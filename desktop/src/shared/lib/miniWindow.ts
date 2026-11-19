// A janela "mini" é a bolha: criada escondida pelo Rust, mostrada quando a principal minimiza ou some.
const MINI_LABEL = "mini";

function inTauri(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

// Canto inferior direito da bolha, em px físicos. Fixo enquanto ela cresce e encolhe; zera ao arrastar.
let corner: { x: number; y: number } | null = null;

/** Redimensiona a bolha mantendo parado o canto inferior direito (onde a bolha mora). */
export async function resizeMiniWindow(width: number, height: number): Promise<void> {
  if (!inTauri()) return;
  const { currentMonitor, getCurrentWindow, PhysicalPosition, PhysicalSize } = await import("@tauri-apps/api/window");
  const win = getCurrentWindow();
  const [pos, size, scale, monitor] = await Promise.all([win.outerPosition(), win.outerSize(), win.scaleFactor(), currentMonitor()]);
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);
  if (w === size.width && h === size.height) return;
  const anchor = corner ?? { x: pos.x + size.width, y: pos.y + size.height };
  corner = anchor;
  // ponytail: só impede sair pelo topo/esquerda; a bolha mora no canto inferior direito.
  const x = Math.max(monitor?.position.x ?? 0, anchor.x - w);
  const y = Math.max(monitor?.position.y ?? 0, anchor.y - h);
  await win.setPosition(new PhysicalPosition(x, y));
  await win.setSize(new PhysicalSize(w, h));
}

/** Arrasta a bolha (ou o painel) e esquece o canto antigo. */
export async function dragMiniWindow(): Promise<void> {
  if (!inTauri()) return;
  corner = null;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().startDragging();
}

/** Bolha parada não rouba o foco; cartão ou painel aberto pode receber teclado. */
export async function setMiniFocus(on: boolean): Promise<void> {
  if (!inTauri()) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const win = getCurrentWindow();
    await win.setFocusable(on);
    if (on) await win.setFocus();
  } catch {
    /* permissão de foco ausente: segue sem teclado */
  }
}

/** Botão "mini" da janela principal: encolhe o DroidNote para a bolha já aberta no painel. */
export async function openMiniPanel(): Promise<void> {
  if (!inTauri()) {
    window.open(`${location.origin}${location.pathname}#mini`, "droidnote-mini", "width=360,height=460");
    return;
  }
  const [{ emitTo }, { getCurrentWindow }] = await Promise.all([import("@tauri-apps/api/event"), import("@tauri-apps/api/window")]);
  await emitTo(MINI_LABEL, "mini-open-panel");
  await getCurrentWindow().minimize();
}

/** Da bolha de volta para a janela principal. */
export async function focusMainWindow(): Promise<void> {
  if (!inTauri()) {
    window.opener?.focus();
    return;
  }
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const main = await WebviewWindow.getByLabel("main");
  if (!main) return;
  await main.unminimize();
  await main.show();
  await main.setFocus();
}

/** Pisca a janela principal na barra de tarefas (reunião detectada com o app minimizado). */
export async function requestAttention(): Promise<void> {
  if (!inTauri()) return;
  try {
    const { getCurrentWindow, UserAttentionType } = await import("@tauri-apps/api/window");
    await getCurrentWindow().requestUserAttention(UserAttentionType.Informational);
  } catch {
    /* opcional */
  }
}

/** Dica da bandeja: menciona a pergunta pendente (o Rust cria a bandeja com id "main"). */
export async function setTrayHint(text: string): Promise<void> {
  if (!inTauri()) return;
  try {
    const { TrayIcon } = await import("@tauri-apps/api/tray");
    await (await TrayIcon.getById("main"))?.setTooltip(text);
  } catch {
    /* bandeja sem id ou sem permissão */
  }
}

export function isMiniRoute(): boolean {
  return window.location.hash === "#mini";
}
