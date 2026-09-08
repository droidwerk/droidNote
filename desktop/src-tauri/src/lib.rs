use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager};

const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(45);
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Clone, Serialize)]
pub struct BackendInfo {
    pub url: String,
    pub token: String,
}

pub struct AppState {
    pub backend: Mutex<Option<BackendInfo>>,
    pub backend_pid: Mutex<Option<u32>>,
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
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            focus_main_window(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            backend: Mutex::new(None),
            backend_pid: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![get_backend])
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
            let _tray = TrayIconBuilder::new()
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
    use super::{parse_ready_line, sidecar_candidates};
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
