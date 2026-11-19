// A janela "mini" é a bolha: criada escondida pelo Rust, mostrada quando a principal minimiza ou some.
const MINI_LABEL = "mini";

function inTauri(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

// Canto inferior direito da bolha (borda externa), em px físicos. Fixo enquanto ela cresce e encolhe; zera ao arrastar.
let corner: { x: number; y: number } | null = null;
// Uma mudança de tamanho por vez: chamadas cruzadas misturavam posição de uma com tamanho de outra.
let queue: Promise<void> = Promise.resolve();

/** Redimensiona a bolha mantendo parado o canto inferior direito, sempre dentro da área útil do monitor. */
export function resizeMiniWindow(width: number, height: number): Promise<void> {
  if (!inTauri()) return Promise.resolve();
  queue = queue.then(() => fitMiniWindow(width, height)).catch(() => undefined);
  return queue;
}

async function fitMiniWindow(width: number, height: number): Promise<void> {
  const { currentMonitor, getCurrentWindow, monitorFromPoint, PhysicalPosition, PhysicalSize } = await import("@tauri-apps/api/window");
  const win = getCurrentWindow();
  const [pos, outer, inner] = await Promise.all([win.outerPosition(), win.outerSize(), win.innerSize()]);
  // setPosition move a borda externa e setSize muda a interna: a moldura invisível do Windows (outer - inner) entra na conta.
  const frameW = outer.width - inner.width;
  const frameH = outer.height - inner.height;
  const anchor = corner ?? { x: pos.x + outer.width, y: pos.y + outer.height };
  const monitor = (await monitorFromPoint(anchor.x - 1, anchor.y - 1)) ?? (await currentMonitor());
  const scale = monitor?.scaleFactor ?? (await win.scaleFactor());
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);
  let x = anchor.x - w - frameW;
  let y = anchor.y - h - frameH;
  if (monitor) {
    const { position: a, size: s } = monitor.workArea;
    // O canto fica dentro da área útil; a borda esquerda/de cima nunca passa do início dela.
    anchor.x = Math.min(Math.max(anchor.x, a.x), a.x + s.width);
    anchor.y = Math.min(Math.max(anchor.y, a.y), a.y + s.height);
    x = Math.max(a.x, anchor.x - w - frameW);
    y = Math.max(a.y, anchor.y - h - frameH);
  }
  corner = anchor;
  if (w === inner.width && h === inner.height && x === pos.x && y === pos.y) return;
  // Posição antes do tamanho: ao trocar de monitor o Windows reescala a janela, e o setSize depois acerta.
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
