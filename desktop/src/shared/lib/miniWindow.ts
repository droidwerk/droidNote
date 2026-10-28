const MINI_LABEL = "mini";
const WIDTH = 380;
const HEIGHT = 200;

function inTauri(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

/** Abre (ou traz para frente) o mini console sempre no topo. */
export async function openMiniWindow(): Promise<void> {
  if (!inTauri()) {
    window.open(`${location.origin}${location.pathname}#mini`, "droidnote-mini", `width=${WIDTH},height=${HEIGHT}`);
    return;
  }
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const existing = await WebviewWindow.getByLabel(MINI_LABEL);
  if (existing) {
    await existing.show();
    await existing.setFocus();
    return;
  }
  const x = Math.max(0, (window.screen.availWidth || 1280) - WIDTH - 24);
  new WebviewWindow(MINI_LABEL, {
    url: "index.html#mini",
    title: "DroidNote",
    width: WIDTH,
    height: HEIGHT,
    x,
    y: 72,
    resizable: false,
    alwaysOnTop: true,
    decorations: false,
    skipTaskbar: true,
    focus: false,
  });
}

export async function closeMiniWindow(): Promise<void> {
  if (!inTauri()) {
    window.close();
    return;
  }
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().close();
}

/** Do mini console de volta para a janela principal. */
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

export function isMiniRoute(): boolean {
  return window.location.hash === "#mini";
}
