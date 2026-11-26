use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri_plugin_dialog::DialogExt;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};

const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(45);
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
const RUN_VALUE: &str = "DroidNote";
const AUTOSTART_ARG: &str = "--autostart";
/// Cápsula parada (32 px) mais o padding de 8 px da caixa medida pela mini.
const BUBBLE_WINDOW: f64 = 48.0;
const BUBBLE_MARGIN: f64 = 24.0;

#[derive(Clone, Serialize)]
pub struct BackendInfo {
    pub url: String,
    pub token: String,
}

pub struct AppState {
    pub backend: Mutex<Option<BackendInfo>>,
    pub backend_pid: Mutex<Option<u32>>,
    /// Último estado publicado da janela principal; evita repetir o evento a cada Resized.
    pub main_state: Mutex<&'static str>,
}

#[tauri::command]
fn get_backend(state: tauri::State<AppState>) -> Result<BackendInfo, String> {
    state
        .backend
        .lock()
        .map_err(|err| err.to_string())?
        .clone()
        .ok_or_else(|| "Backend ainda não está pronto".into())
}

#[derive(Clone, Deserialize)]
pub struct SaveFilter {
    pub name: String,
    pub extensions: Vec<String>,
}

/// Exportação: o diálogo "Salvar" roda aqui no Rust e só o caminho que o usuário
/// escolheu é gravado. A interface nunca manda um caminho, então nada no webview
/// consegue escrever em outro lugar do disco. Devolve o caminho gravado, ou None
/// quando a pessoa cancelou.
#[tauri::command]
async fn save_export_file(
    app: tauri::AppHandle,
    name: String,
    filters: Vec<SaveFilter>,
    bytes: Vec<u8>,
) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut builder = app.dialog().file().set_file_name(&name);
        for filter in &filters {
            let extensions: Vec<&str> = filter.extensions.iter().map(String::as_str).collect();
            builder = builder.add_filter(&filter.name, &extensions);
        }
        let Some(chosen) = builder.blocking_save_file() else {
            return Ok(None);
        };
        let path = chosen.into_path().map_err(|err| err.to_string())?;
        std::fs::write(&path, bytes).map_err(|err| err.to_string())?;
        Ok(Some(path.to_string_lossy().to_string()))
    })
    .await
    .map_err(|err| err.to_string())?
}

/// Valor gravado em HKCU\...\Run: exe entre aspas + --autostart.
fn run_value(exe: &std::path::Path) -> String {
    format!("\"{}\" {AUTOSTART_ARG}", exe.display())
}

fn reg(args: &[&str]) -> std::io::Result<std::process::ExitStatus> {
    // Caminho absoluto: um reg.exe plantado na pasta do app não é usado.
    let root = std::env::var_os("SystemRoot").unwrap_or_else(|| r"C:\Windows".into());
    let mut command = Command::new(PathBuf::from(root).join("System32").join("reg.exe"));
    command.args(args).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command.status()
}

fn autostart_registered() -> bool {
    reg(&["query", RUN_KEY, "/v", RUN_VALUE])
        .map(|status| status.success())
        .unwrap_or(false)
}

/// None = não suportado (build de debug: nunca registrar target/debug no Run).
#[tauri::command]
fn autostart_get() -> Option<bool> {
    if cfg!(debug_assertions) {
        return None;
    }
    Some(autostart_registered())
}

#[tauri::command]
fn autostart_set(enabled: bool) -> Result<bool, String> {
    if cfg!(debug_assertions) {
        return Err("unsupported".into());
    }
    if enabled {
        let exe = std::env::current_exe().map_err(|err| err.to_string())?;
        let value = run_value(&exe);
        reg(&["add", RUN_KEY, "/v", RUN_VALUE, "/t", "REG_SZ", "/d", &value, "/f"])
            .map_err(|err| err.to_string())?;
    } else {
        // Apagar valor inexistente falha no reg.exe; o query abaixo decide.
        let _ = reg(&["delete", RUN_KEY, "/v", RUN_VALUE, "/f"]);
    }
    let now = autostart_registered();
    if now == enabled {
        Ok(now)
    } else {
        Err("Não foi possível alterar a inicialização com o Windows".into())
    }
}

fn external_backend() -> Option<BackendInfo> {
    match std::env::var("DROIDNOTE_EXTERNAL_BACKEND") {
        Ok(value) if value == "1" => Some(BackendInfo {
            url: std::env::var("DROIDNOTE_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:8765".to_string()),
            token: std::env::var("DROIDNOTE_TOKEN")
                .unwrap_or_else(|_| "dev-token".to_string()),
        }),
        _ => None,
    }
}

fn data_folder() -> PathBuf {
    let folder = if cfg!(debug_assertions) {
        "DroidNote-dev"
    } else {
        "DroidNote"
    };
    std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(folder)
}

fn boot_error(msg: &str) {
    let dir = data_folder();
    let _ = std::fs::create_dir_all(&dir);
    let _ = std::fs::write(dir.join("boot-error.log"), msg);
    append_backend_log(&format!("BOOT_ERROR {msg}"));
}

fn append_backend_log(line: &str) {
    let path = data_folder().join("logs").join("backend.log");
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{line}");
    }
}

fn sidecar_candidates(resource_dir: Option<PathBuf>, exe_dir: Option<PathBuf>) -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Some(dir) = resource_dir {
        roots.push(dir.clone());
        roots.push(dir.join("resources"));
    }
    if let Some(dir) = exe_dir {
        roots.push(dir.clone());
        roots.push(dir.join("resources"));
    }
    let mut paths = Vec::new();
    for root in roots {
        paths.push(
            root.join("droidnote-backend")
                .join("droidnote-backend.exe"),
        );
    }
    paths
}

fn kill_backend(pid: Option<u32>) {
    let Some(pid) = pid else {
        return;
    };
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string(), "/T"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();
    }
}

fn parse_ready_line(line: &str) -> Option<BackendInfo> {
    let rest = line.strip_prefix("DROIDNOTE_READY ")?;
    let value: serde_json::Value = serde_json::from_str(rest).ok()?;
    let port = value.get("port").and_then(|item| item.as_u64()).unwrap_or(8765);
    let token = value
        .get("token")
        .and_then(|item| item.as_str())
        .unwrap_or("")
        .to_string();
    let host = value
        .get("host")
        .and_then(|item| item.as_str())
        .unwrap_or("127.0.0.1");
    Some(BackendInfo {
        url: format!("http://{host}:{port}"),
        token,
    })
}

fn spawn_backend(resource_dir: Option<PathBuf>) -> Result<(BackendInfo, u32), String> {
    let mut command = backend_command(resource_dir)?;
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|err| {
        let msg = format!(
            "Não foi possível iniciar o motor local ({err}). Se o Windows Defender bloqueou o DroidNote, permita o aplicativo e tente de novo."
        );
        boot_error(&msg);
        msg
    })?;
    let pid = child.id();
    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                append_backend_log(&line);
            }
        });
    }
    let stdout = child.stdout.take().ok_or_else(|| {
        let msg = "Backend sem stdout".to_string();
        boot_error(&msg);
        msg
    })?;
    let (tx, rx) = mpsc::channel::<Result<BackendInfo, String>>();
    thread::spawn(move || {
        let mut lines = BufReader::new(stdout).lines();
        while let Some(line) = lines.next() {
            let line = match line {
                Ok(line) => line,
                Err(err) => {
                    let _ = tx.send(Err(err.to_string()));
                    return;
                }
            };
            if line.starts_with("DROIDNOTE_READY ") {
                append_backend_log("DROIDNOTE_READY [redacted]");
                match parse_ready_line(&line) {
                    Some(info) => {
                        let _ = tx.send(Ok(info));
                    }
                    None => {
                        let _ = tx.send(Err("DROIDNOTE_READY inválido".into()));
                    }
                }
                for extra in lines.map_while(Result::ok) {
                    append_backend_log(&extra);
                }
                return;
            }
            append_backend_log(&line);
        }
        let _ = tx.send(Err("Backend não publicou DROIDNOTE_READY".into()));
    });
    match rx.recv_timeout(BACKEND_READY_TIMEOUT) {
        Ok(Ok(info)) => {
            thread::spawn(move || {
                let _ = child.wait();
            });
            Ok((info, pid))
        }
        Ok(Err(msg)) => {
            kill_backend(Some(pid));
            let _ = child.kill();
            let friendly = format!(
                "{msg}. Se o antivírus quarentenou um arquivo, restaure o DroidNote e tente de novo."
            );
            boot_error(&friendly);
            Err(friendly)
        }
        Err(_) => {
            kill_backend(Some(pid));
            let _ = child.kill();
            let msg = "O DroidNote demorou demais para iniciar. Se o Windows bloqueou um componente, permita o DroidNote e o droidnote-backend no Defender e tente de novo.";
            boot_error(msg);
            Err(msg.into())
        }
    }
}

fn backend_command(resource_dir: Option<PathBuf>) -> Result<Command, String> {
    if cfg!(debug_assertions) {
        let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend");
        let mut command = Command::new("python");
        command.args(["-m", "app"]);
        command.current_dir(&backend_dir);
        command.env("PYTHONPATH", &backend_dir);
        if let Some(appdata) = std::env::var_os("APPDATA") {
            command.env(
                "DROIDNOTE_DATA_DIR",
                PathBuf::from(appdata).join("DroidNote-dev"),
            );
        }
        return Ok(command);
    }
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(PathBuf::from));
    let tried = sidecar_candidates(resource_dir, exe_dir.clone());
    let sidecar = tried.iter().find(|path| path.exists()).cloned();
    let Some(sidecar) = sidecar else {
        let msg = format!(
            "O motor local não foi encontrado. Reinstale o DroidNote. Caminhos tentados: {}",
            tried
                .iter()
                .map(|path| path.display().to_string())
                .collect::<Vec<_>>()
                .join(" | ")
        );
        boot_error(&msg);
        return Err(msg);
    };
    let mut command = Command::new(&sidecar);
    if let Some(dir) = sidecar.parent() {
        command.current_dir(dir);
    }
    Ok(command)
}

fn focus_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
    set_main_state(app, "shown");
}

/// Publica "main-window-state" e mostra/esconde a bolha aqui no Rust: o webview
/// principal minimizado ou oculto tem JS estrangulado e reagiria tarde.
fn set_main_state(app: &tauri::AppHandle, state: &'static str) {
    let away = matches!(state, "minimized" | "hidden");
    let bubble = app.get_webview_window("mini");
    // Antes do dedup: um segundo "minimized" ainda resgata uma bolha perdida.
    if let (true, Some(bubble)) = (away, &bubble) {
        raise_bubble(bubble);
    }
    if let Ok(mut last) = app.state::<AppState>().main_state.lock() {
        if *last == state {
            return;
        }
        *last = state;
    }
    if let (false, Some(bubble)) = (away, &bubble) {
        let _ = bubble.hide();
    }
    let _ = app.emit("main-window-state", serde_json::json!({ "state": state }));
}

/// Traz a bolha de volta: desminimiza, mostra e reafirma o topmost. O tao só aplica
/// always_on_top quando o valor muda, então false -> true força o SetWindowPos.
fn raise_bubble(bubble: &tauri::WebviewWindow) {
    let _ = bubble.unminimize();
    let _ = bubble.show();
    let _ = bubble.set_always_on_top(false);
    let _ = bubble.set_always_on_top(true);
}

/// Pergunta pendente (silêncio, música, fim do evento): a bolha aparece mesmo com a principal aberta.
#[tauri::command]
fn surface_mini(app: tauri::AppHandle) {
    if let Some(bubble) = app.get_webview_window("mini") {
        raise_bubble(&bubble);
    }
}

fn on_main_window_event(window: &tauri::Window, event: &WindowEvent) {
    let app = window.app_handle();
    match event {
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            let _ = window.hide();
            set_main_state(app, "hidden");
        }
        // Windows não tem evento de minimizar: minimizar gera Resized 0x0.
        WindowEvent::Resized(_) => {
            if window.is_minimized().unwrap_or(false) {
                set_main_state(app, "minimized");
            } else if window.is_visible().unwrap_or(false) {
                set_main_state(app, "restored");
            }
        }
        // Foco chega também com a janela minimizada (clique na barra): não esconde a bolha nesse caso.
        WindowEvent::Focused(true)
            if !window.is_minimized().unwrap_or(false) && window.is_visible().unwrap_or(false) =>
        {
            set_main_state(app, "restored")
        }
        _ => {}
    }
}

/// Bolha criada oculta no início, para o WS dela já estar conectado quando aparecer.
fn create_bubble(app: &tauri::App) -> tauri::Result<()> {
    let builder =
        WebviewWindowBuilder::new(app, "mini", WebviewUrl::App("index.html#mini".into()))
            .title("DroidNote")
            .inner_size(BUBBLE_WINDOW, BUBBLE_WINDOW)
            .visible(false)
            .always_on_top(true)
            .decorations(false)
            .skip_taskbar(true)
            .transparent(true)
            .shadow(false)
            .focusable(false)
            // Sem botão de minimizar: Win+Down/Win+M com a bolha focada sumiam com ela (sem barra de tarefas).
            .minimizable(false)
            .resizable(false);
    let bubble = builder.build()?;
    // Em px físicos e pela borda externa: posição lógica converte pela escala do monitor
    // onde a janela nasceu, e a moldura invisível do Windows deixa a borda externa maior que 48.
    if let Some(monitor) = app.primary_monitor()? {
        let area = monitor.work_area();
        let outer = bubble.outer_size()?;
        let margin = (BUBBLE_MARGIN * monitor.scale_factor()).round() as i32;
        bubble.set_position(tauri::PhysicalPosition::new(
            area.position.x + area.size.width as i32 - outer.width as i32 - margin,
            area.position.y + area.size.height as i32 - outer.height as i32 - margin,
        ))?;
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            if !argv.iter().any(|arg| arg == AUTOSTART_ARG) {
                focus_main_window(app);
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState {
            backend: Mutex::new(None),
            backend_pid: Mutex::new(None),
            main_state: Mutex::new(""),
        })
        .invoke_handler(tauri::generate_handler![
            get_backend,
            save_export_file,
            autostart_get,
            autostart_set,
            surface_mini
        ])
        .on_window_event(|window, event| {
            if window.label() == "main" {
                on_main_window_event(window, event);
            }
        })
        .setup(|app| {
            let resource_dir = app.path().resource_dir().ok();
            let info = match external_backend() {
                Some(info) => info,
                None => {
                    let (info, pid) = spawn_backend(resource_dir).map_err(|err| {
                        boot_error(&err);
                        err
                    })?;
                    if let Ok(mut slot) = app.state::<AppState>().backend_pid.lock() {
                        *slot = Some(pid);
                    }
                    info
                }
            };
            if let Ok(mut slot) = app.state::<AppState>().backend.lock() {
                *slot = Some(info.clone());
            }
            let quit = MenuItem::with_id(app, "quit", "Sair", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "Abrir DroidNote", true, None::<&str>)?;
            let toggle =
                MenuItem::with_id(app, "toggle", "Ligar/Desligar captura", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &toggle, &quit])?;
            let _tray = TrayIconBuilder::with_id("main")
                .menu(&menu)
                .tooltip("DroidNote")
                .icon(app.default_window_icon().cloned().expect("icon"))
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        let pid = app
                            .state::<AppState>()
                            .backend_pid
                            .lock()
                            .ok()
                            .and_then(|guard| *guard);
                        kill_backend(pid);
                        app.exit(0);
                    }
                    "show" => focus_main_window(app),
                    "toggle" => {
                        let _ = app.emit("tray-toggle-capture", ());
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        focus_main_window(tray.app_handle());
                    }
                })
                .build(app)?;
            create_bubble(app)?;
            // Outra janela topmost (Teams, Meet, Zoom) cobre a bolha não ativável; reafirma a cada 4 s.
            // ponytail: polling; trocar por SetWinEventHook(EVENT_SYSTEM_FOREGROUND) se a CPU pesar.
            let handle = app.handle().clone();
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(4));
                if let Some(bubble) = handle.get_webview_window("mini") {
                    if bubble.is_visible().unwrap_or(false) {
                        let _ = bubble.set_always_on_top(false);
                        let _ = bubble.set_always_on_top(true);
                    }
                }
            });
            // A janela nasce oculta (tauri.conf.json) e aparece aqui, já pronta, sem flash.
            // Também no --autostart: iniciar com o Windows abre o app, não só a bandeja.
            focus_main_window(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("erro ao iniciar DroidNote")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let pid = app
                    .state::<AppState>()
                    .backend_pid
                    .lock()
                    .ok()
                    .and_then(|guard| *guard);
                kill_backend(pid);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::{parse_ready_line, run_value, sidecar_candidates};

    #[test]
    fn run_value_quotes_exe_and_adds_flag() {
        let exe = PathBuf::from(r"C:\Program Files\DroidNote\DroidNote.exe");
        assert_eq!(
            run_value(&exe),
            r#""C:\Program Files\DroidNote\DroidNote.exe" --autostart"#
        );
    }
    use std::path::PathBuf;

    #[test]
    fn nsis_layout_includes_resources_sidecar() {
        let install = PathBuf::from(r"C:\Users\tester\AppData\Local\DroidNote");
        let paths = sidecar_candidates(Some(install.clone()), Some(install));
        assert!(
            paths.iter().any(|path| path.ends_with(
                PathBuf::from("resources")
                    .join("droidnote-backend")
                    .join("droidnote-backend.exe")
            )),
            "missing NSIS sidecar path in {paths:?}"
        );
    }

    #[test]
    fn parse_ready_line_reads_port_and_token() {
        let info = parse_ready_line(
            r#"DROIDNOTE_READY {"host":"127.0.0.1","port":1234,"token":"abc"}"#,
        )
        .expect("ready line");
        assert_eq!(info.url, "http://127.0.0.1:1234");
        assert_eq!(info.token, "abc");
    }

    #[test]
    fn parse_ready_line_ignores_noise() {
        assert!(parse_ready_line("hello").is_none());
    }
}
