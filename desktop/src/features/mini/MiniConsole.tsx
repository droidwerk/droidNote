import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";

import { api, askChat, openTranscriptSocket, setBackend } from "../../shared/api/client";
import type { Brief, CaptureState } from "../../shared/api/types";
import { useI18n } from "../../shared/i18n";
import { dragMiniWindow, focusMainWindow, resizeMiniWindow, setMiniFocus } from "../../shared/lib/miniWindow";
import { clusterToken, voiceName } from "../../shared/lib/voices";
import { AiThinking } from "../../shared/ui/AiThinking";
import { Markdown } from "../../shared/ui/Markdown";
import { Icon, type IconName } from "../../shared/ui/Icon";
import { MEETING_DETECTION_ENABLED } from "../meeting/MeetingBanner";

interface Line {
  id: string;
  text: string;
  cluster: string | null;
  name: string | null;
}

type Pane = "live" | "ask" | "context";
type Marker = "decision" | "task" | "important" | "question";
/** bubble = só a bolha; record = cartão "Gravar" (clique parado); panel = mini painel. */
type View = "bubble" | "record" | "panel";
type AlertKind = "silence" | "music";

const MARKERS: { id: Marker; icon: IconName }[] = [
  { id: "decision", icon: "check" },
  { id: "task", icon: "tasks" },
  { id: "important", icon: "spark" },
  { id: "question", icon: "chat" },
];
const QUICK_ASKS = ["sofar", "decided", "missed", "suggest"] as const;
const TAIL = 8;
const MEETING_CARD_MS = 20_000;
const IN_TAURI = "__TAURI_INTERNALS__" in window;

/** Bolha flutuante: mostra se grava, pergunta quando precisa e cresce até o mini painel. */
export function MiniConsole() {
  const { t, locale } = useI18n();
  const [ready, setReady] = useState(false);
  const [capture, setCapture] = useState<CaptureState | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [note, setNote] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<View>("bubble");
  const [meeting, setMeeting] = useState<string | null>(null);
  // Com a janela principal à vista a bolha fica escondida e o aviso de reunião é dela.
  const [visible, setVisible] = useState(!IN_TAURI);
  const [alert, setAlert] = useState<AlertKind | null>(null);
  const [level, setLevel] = useState(0);
  const [marksOpen, setMarksOpen] = useState(false);
  const [marked, setMarked] = useState("");
  const [pane, setPane] = useState<Pane>("live");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const tail = useRef<HTMLOListElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const bubble = useRef<HTMLButtonElement>(null);
  const press = useRef<{ x: number; y: number; dragged: boolean } | null>(null);
  const markBtn = useRef<HTMLButtonElement>(null);
  const elapsed = useElapsed(capture?.recording ? capture.started_at ?? null : null);

  useEffect(() => {
    document.documentElement.classList.add("is-mini");
    let cancelled = false;
    void (async () => {
      if (IN_TAURI) {
        const { invoke } = await import("@tauri-apps/api/core");
        setBackend(await invoke<{ url: string; token: string }>("get_backend"));
      }
      if (cancelled) return;
      try {
        setCapture(await api.captureState());
      } catch {
        /* backend ainda subindo */
      }
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // A janela segue o tamanho do conteúdo, presa no canto da bolha.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const fit = () => void resizeMiniWindow(el.offsetWidth, el.offsetHeight).catch(() => undefined);
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // O Rust também mostra/esconde; aqui repetimos para não depender da janela principal acordada.
  useEffect(() => {
    if (!IN_TAURI) return undefined;
    const offs: (() => void)[] = [];
    let dead = false;
    void (async () => {
      const [{ listen }, { getCurrentWindow, Window }] = await Promise.all([
        import("@tauri-apps/api/event"),
        import("@tauri-apps/api/window"),
      ]);
      const self = getCurrentWindow();
      const apply = (state: string) => {
        if (state === "minimized" || state === "hidden") {
          setVisible(true);
          void self.show();
        } else if (state === "restored" || state === "shown") {
          setVisible(false);
          setView("bubble");
          void self.hide();
          void setMiniFocus(false);
        }
      };
      offs.push(await listen<{ state: string }>("main-window-state", (event) => apply(event.payload?.state ?? "")));
      offs.push(
        await listen("mini-open-panel", () => {
          setView("panel");
          void setMiniFocus(true);
        }),
      );
      if (dead) offs.forEach((off) => off());
      const main = await Window.getByLabel("main");
      if (main && !dead) apply((await main.isMinimized()) || !(await main.isVisible()) ? "minimized" : "shown");
    })();
    return () => {
      dead = true;
      offs.forEach((off) => off());
    };
  }, []);

  useEffect(() => {
    if (!ready) return undefined;
    return openTranscriptSocket((event) => {
      if (event.type === "capture" || event.type === "hello") {
        setCapture((current) => ({
          ...(current ?? { mic_only: false, warning: null }),
          recording: Boolean(event.recording),
          paused: Boolean(event.paused),
          session_id: typeof event.session_id === "string" ? event.session_id : current?.session_id ?? null,
          started_at: typeof event.started_at === "string" ? event.started_at : null,
        }) as CaptureState);
        if (!event.recording || event.paused) setLevel(0);
        if (!event.recording) {
          setAlert(null);
          setView((current) => (current === "panel" ? "bubble" : current));
        }
        if (event.recording) setMeeting(null);
      }
      if (event.type === "hello" && event.idle_alert && typeof event.idle_alert === "object") {
        setAlert((event.idle_alert as { kind?: string }).kind === "music" ? "music" : "silence");
      }
      if (event.type === "monitor" && typeof event.rms === "number") {
        // raiz comprime a faixa: fala normal enche o anel sem saturar.
        setLevel(Math.min(1, Math.sqrt(event.rms) * 2.5));
      }
      if (event.type === "meeting") {
        // "Gravar" também manda detected antes de começar: só "Perguntar" abre o cartão.
        if (event.status === "detected" && event.mode === "ask") setMeeting(typeof event.app === "string" ? event.app : "");
        else if (event.status === "dismissed" || event.status === "auto-started") setMeeting(null);
      }
      if (event.type === "idle_alert") {
        setAlert(event.status === "asked" ? (event.kind === "music" ? "music" : "silence") : null);
      }
      if (event.type === "segment" && event.segment && typeof event.segment === "object") {
        const segment = event.segment as { id?: string; text?: string; speaker_cluster?: string | null; speaker_name?: string | null };
        if (segment.text) {
          const next: Line = {
            id: segment.id ?? `${Date.now()}`,
            text: segment.text,
            cluster: segment.speaker_cluster ?? null,
            name: segment.speaker_name ?? null,
          };
          setLines((current) => [...current.filter((item) => item.id !== next.id), next].slice(-TAIL));
        }
      }
    });
  }, [ready]);

  const recording = Boolean(capture?.recording);
  const paused = recording && Boolean(capture?.paused);
  const sessionId = capture?.session_id ?? null;
  const card = alert ? "alert" : MEETING_DETECTION_ENABLED && meeting !== null && visible && !recording ? "meeting" : view !== "bubble" && !recording ? "record" : null;
  const panel = view === "panel" && recording && !alert;

  // Cartão de reunião some em 20 s, como o aviso da janela principal; só conta com a bolha à vista.
  const meetingShown = card === "meeting";
  useEffect(() => {
    if (!meetingShown) return undefined;
    const timer = window.setTimeout(() => {
      setMeeting(null);
      void api.dismissMeeting().catch(() => undefined);
    }, MEETING_CARD_MS);
    return () => window.clearTimeout(timer);
  }, [meetingShown, meeting]);

  useEffect(() => {
    if (!sessionId) {
      setBrief(null);
      return;
    }
    setLines([]);
    setAnswer("");
    setChatId(null);
    setMarked("");
    void api.brief({ sessionId }).then(setBrief).catch(() => setBrief(null));
  }, [sessionId]);

  useEffect(() => {
    tail.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [lines, panel, pane]);

  // Foco segue a vista: painel na aba ativa, cartão no primeiro botão, recolher volta à bolha.
  const shown = panel ? "panel" : card ?? "bubble";
  const previous = useRef(shown);
  useEffect(() => {
    const was = previous.current;
    previous.current = shown;
    if (was === shown) return;
    const root = box.current;
    if (shown === "panel") root?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus();
    else if (shown === "record") root?.querySelector<HTMLElement>(".bubble-card .button-primary")?.focus();
    // O painel some do DOM antes daqui: o foco cai no body e volta para a bolha.
    else if (shown === "bubble" && (document.activeElement === document.body || root?.contains(document.activeElement))) bubble.current?.focus();
  }, [shown]);

  const collapse = () => {
    setView("bubble");
    setMarksOpen(false);
  };

  // Lista de marcadores: abre no primeiro; ao escolher ou Esc, o foco volta para "Marcar".
  useEffect(() => {
    if (marksOpen) box.current?.querySelector<HTMLElement>("#bubble-marks button")?.focus();
  }, [marksOpen]);
  const closeMarks = () => {
    setMarksOpen(false);
    markBtn.current?.focus();
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (marksOpen) closeMarks();
      else if (view !== "bubble") collapse();
      else return;
      event.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const nameOf = (cluster: string | null, name: string | null) => name ?? (cluster ? voiceName(cluster) : "");

  const blink = (key: string) => {
    setFlash(key);
    window.setTimeout(() => setFlash((current) => (current === key ? null : current)), 900);
  };

  const saveNote = async (text: string, key = "note", kind: Marker | null = null) => {
    const cleaned = text.trim();
    if (!cleaned || !sessionId || !recording) return;
    await api.addNote(sessionId, cleaned, null, kind);
    blink(key);
  };

  const mark = async (marker: Marker) => {
    // Com texto digitado, ele vira a anotação com esse tipo; sem texto, marca o momento.
    const text = note.trim() || t(`mini.markerMoment_${marker}`);
    await saveNote(text, marker, marker);
    setNote("");
    closeMarks();
    setMarked(t("mini.marked", { marker: t(`mini.marker_${marker}`), time: formatTimecode(elapsed) }));
  };

  const ask = async (text: string) => {
    const cleaned = text.trim();
    if (!cleaned || asking || !sessionId) return;
    setAsking(true);
    setAnswer("");
    setQuestion("");
    try {
      const result = await askChat(
        { message: cleaned, chat_id: chatId, session_id: sessionId, ui_language: locale },
        (token) => setAnswer((current) => current + token),
      );
      setChatId(result.chat.id);
    } catch (err) {
      setAnswer(err instanceof Error ? err.message : t("chat.fail"));
    } finally {
      setAsking(false);
    }
  };

  const run = async (action: () => Promise<CaptureState | unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await action();
      if (result && typeof result === "object" && "recording" in result) setCapture(result as CaptureState);
    } catch {
      /* o estado real chega pelo WS */
    } finally {
      setBusy(false);
    }
  };

  const record = (title?: string) => {
    setMeeting(null);
    setView("bubble");
    void run(() => api.startCapture({ capture_mode: "meeting", title }));
  };
  const end = () => {
    setAlert(null);
    collapse();
    void run(() => api.stopCapture());
  };

  const onBubble = () => {
    if (press.current?.dragged) return;
    void setMiniFocus(true);
    if (card === "alert" || card === "meeting") {
      box.current?.querySelector<HTMLElement>(".bubble-card .button")?.focus();
      return;
    }
    setView((current) => (recording ? "panel" : current === "record" ? "bubble" : "record"));
  };

  const bubbleLook = alert ? "is-ask" : recording && !paused ? "is-rec" : "is-idle";
  const bubbleLabel = alert
    ? t("mini.bubbleAsk")
    : paused
      ? t("mini.bubblePaused")
      : recording
        ? t("mini.bubbleRec")
        : t("mini.bubbleIdle");

  return (
    <div className="bubble-box" ref={box}>
      {card === "record" ? (
        <div className="bubble-card" role="group" aria-labelledby="bubble-record-title">
          <div className="bubble-card-top">
            <strong id="bubble-record-title">{t("mini.idleTitle")}</strong>
            <button type="button" className="mini-icon" aria-label={t("mini.close")} title={t("mini.close")} onClick={collapse}>
              <Icon name="close" size={14} />
            </button>
          </div>
          <button type="button" className="button button-primary button-sm" disabled={busy} onClick={() => record()}>
            {t("mini.record")}
          </button>
        </div>
      ) : null}
      {card === "meeting" ? (
        <div className="bubble-card" role="group" aria-labelledby="bubble-meeting-title">
          <div>
            <strong id="bubble-meeting-title">{t("mini.meetingTitle")}</strong>
            {meeting ? <p>{t("mini.meetingLine", { app: meeting })}</p> : null}
          </div>
          <div className="bubble-card-acts is-two">
            <button
              type="button"
              className="button button-primary button-sm"
              disabled={busy}
              onClick={() =>
                record(
                  meeting
                    ? `${meeting} · ${new Date().toLocaleString(document.documentElement.lang || undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`
                    : undefined,
                )
              }
            >
              {t("mini.record")}
            </button>
            <button
              type="button"
              className="button button-ghost button-sm"
              onClick={() => {
                setMeeting(null);
                void api.dismissMeeting().catch(() => undefined);
              }}
            >
              {t("mini.notNow")}
            </button>
          </div>
        </div>
      ) : null}
      {card === "alert" ? (
        <div className="bubble-card is-ask" role="group" aria-labelledby="bubble-alert-title" aria-describedby="bubble-alert-line">
          <div>
            <strong id="bubble-alert-title">{t("mini.alertTitle")}</strong>
            <p id="bubble-alert-line">{alert === "music" ? t("mini.alertMusic") : t("mini.alertSilence")}</p>
          </div>
          <div className="bubble-card-acts">
            <button
              type="button"
              className="button button-ghost button-sm"
              disabled={busy}
              onClick={() => {
                setAlert(null);
                void run(() => api.dismissIdleAlert());
              }}
            >
              {t("mini.alertContinue")}
            </button>
            <button type="button" className="button button-primary button-sm" disabled={busy} onClick={end}>
              {t("mini.alertEnd")}
            </button>
          </div>
        </div>
      ) : null}

      {panel ? (
        <div className={paused ? "mini is-expanded bubble-panel" : "mini is-expanded is-live bubble-panel"} role="group" aria-label={t("mini.panelAria")}>
          <header className="mini-head" onPointerDown={(event) => !(event.target as HTMLElement).closest("button") && void dragMiniWindow()}>
            <span className="state-led" aria-hidden />
            <span className="mini-state">{paused ? t("mini.paused") : t("mini.recording")}</span>
            <span className="mini-clock">{formatTimecode(elapsed)}</span>
            <button type="button" className="mini-icon" title={t("mini.openMain")} aria-label={t("mini.openMain")} onClick={() => void focusMainWindow()}>
              <Icon name="export" size={14} />
            </button>
            <button type="button" className="button button-ghost button-sm" onClick={collapse}>
              {t("mini.collapse")}
            </button>
          </header>
          <nav className="mini-tabs" role="tablist" aria-label={t("mini.tabsAria")}>
            {(["live", "ask", "context"] as const).map((id, index, all) => (
              <button
                key={id}
                id={`bubble-tab-${id}`}
                type="button"
                role="tab"
                aria-controls="bubble-pane"
                aria-selected={pane === id}
                tabIndex={pane === id ? 0 : -1}
                className={pane === id ? "is-on" : ""}
                onClick={() => setPane(id)}
                onKeyDown={(event) => {
                  const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
                  if (!step) return;
                  event.preventDefault();
                  const next = all[(index + step + all.length) % all.length] ?? id;
                  setPane(next);
                  (event.currentTarget.parentElement?.children[all.indexOf(next)] as HTMLElement | undefined)?.focus();
                }}
              >
                {t(`mini.pane_${id}`)}
                {id === "context" && brief?.pending.length ? <span className="tab-count">{brief.pending.length}</span> : null}
              </button>
            ))}
          </nav>
          <div className="mini-pane" id="bubble-pane" role="tabpanel" aria-labelledby={`bubble-tab-${pane}`}>
            {pane === "live" ? (
              lines.length ? (
                <ol className="mini-tail" ref={tail}>
                  {lines.map((item) => (
                    <li key={item.id} style={{ "--voice": item.cluster ? clusterToken(item.cluster) : "var(--muted)" } as CSSProperties}>
                      <b>{nameOf(item.cluster, item.name)}</b>
                      <span>{item.text}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mini-empty">{paused ? t("mini.alertPaused") : t("mini.listening")}</p>
              )
            ) : null}
            {pane === "ask" ? (
              <div className="mini-ask">
                {!sessionId ? <p className="mini-empty">{t("mini.askNeedsSession")}</p> : null}
                {sessionId && !answer && !asking ? (
                  <div className="mini-quick">
                    {QUICK_ASKS.map((id) => (
                      <button key={id} type="button" className="chip" onClick={() => void ask(t(`mini.ask_${id}`))}>
                        {t(`mini.askLabel_${id}`)}
                      </button>
                    ))}
                  </div>
                ) : null}
                {asking && !answer ? <AiThinking compact lines={3} steps={[t("ai.listenBack"), t("ai.answer")]} /> : null}
                {answer ? (
                  <div className="mini-answer" aria-live="polite">
                    <Markdown text={answer} />
                    {!asking ? (
                      <button type="button" className="mini-link" onClick={() => setAnswer("")}>
                        {t("mini.askAgain")}
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <form
                  className="mini-ask-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void ask(question);
                  }}
                >
                  <input
                    className="mini-note"
                    value={question}
                    disabled={!sessionId || asking}
                    placeholder={t("mini.askPlaceholder")}
                    aria-label={t("mini.askPlaceholder")}
                    onChange={(event) => setQuestion(event.target.value)}
                  />
                  <button type="submit" className="mini-send" disabled={!question.trim() || asking || !sessionId} aria-label={t("chat.send")}>
                    <Icon name="arrow" size={14} />
                  </button>
                </form>
              </div>
            ) : null}
            {pane === "context" ? (
              <div className="mini-context">
                {!brief || !brief.related.length ? (
                  <p className="mini-empty">{t("brief.firstTime")}</p>
                ) : (
                  <>
                    {brief.pending.length ? (
                      <>
                        <h4>{t("brief.pending")}</h4>
                        <ul>
                          {brief.pending.slice(0, 8).map((task) => (
                            <li key={task.id}>
                              {task.text}
                              {task.owner ? <small> · {task.owner}</small> : null}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {brief.related[0]?.decisions.length ? (
                      <>
                        <h4>{t("brief.lastTime")}</h4>
                        <ul>
                          {brief.related[0].decisions.slice(0, 5).map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </>
                )}
              </div>
            ) : null}
          </div>

          <div className="bubble-mark">
            <div className="bubble-mark-top">
              <button
                ref={markBtn}
                type="button"
                className="button button-ghost button-sm"
                aria-expanded={marksOpen}
                aria-controls="bubble-marks"
                onClick={() => setMarksOpen((value) => !value)}
              >
                {t("mini.mark")}
              </button>
              <span className="bubble-mark-done" aria-live="polite">{marked}</span>
            </div>
            {marksOpen ? (
              <div className="mini-markers" id="bubble-marks" role="group" aria-label={t("mini.markersAria")}>
                {MARKERS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={flash === item.id ? "mini-marker is-done" : "mini-marker"}
                    title={t(`mini.markerHint_${item.id}`)}
                    onClick={() => void mark(item.id)}
                  >
                    <Icon name={item.icon} size={12} />
                    {t(`mini.marker_${item.id}`)}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <footer className="mini-foot">
            <input
              className={flash === "note" ? "mini-note is-saved" : "mini-note"}
              value={note}
              placeholder={t("mini.notePlaceholder")}
              aria-label={t("mini.notePlaceholder")}
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  const text = note;
                  setNote("");
                  void saveNote(text);
                }
              }}
            />
            {paused ? (
              <button type="button" className="button button-primary button-sm" disabled={busy} onClick={() => void run(() => api.resumeCapture())}>
                {t("mini.resume")}
              </button>
            ) : null}
            <button
              type="button"
              className="mini-rec is-live"
              disabled={busy}
              title={t("mini.alertEnd")}
              aria-label={t("mini.alertEnd")}
              onClick={end}
            >
              <span className="reactor-stop" />
            </button>
          </footer>
        </div>
      ) : (
        <div className="bubble-slot">
          {paused && !alert ? <span className="bubble-chip">{t("mini.paused")}</span> : null}
          <button
            ref={bubble}
            type="button"
            className={`bubble ${bubbleLook}`}
            style={{ "--level": level } as CSSProperties}
            aria-label={bubbleLabel}
            aria-expanded={card !== null}
            onPointerDown={(event) => {
              press.current = { x: event.screenX, y: event.screenY, dragged: false };
            }}
            onPointerMove={(event) => {
              const start = press.current;
              if (!start || start.dragged || event.buttons !== 1) return;
              if (Math.hypot(event.screenX - start.x, event.screenY - start.y) < 4) return;
              start.dragged = true;
              void dragMiniWindow();
            }}
            onClick={onBubble}
          >
            {alert ? (
              <span className="bubble-q" aria-hidden>
                ?
              </span>
            ) : paused ? (
              <Icon name="pause" size={16} />
            ) : (
              <span className="bubble-dot" aria-hidden />
            )}
          </button>
        </div>
      )}
    </div>
  );
}

function useElapsed(startedAt: string | null): number {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    if (!startedAt) {
      setMs(0);
      return undefined;
    }
    const origin = Date.parse(startedAt);
    const tick = () => setMs(Math.max(0, Date.now() - origin));
    tick();
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return ms;
}

function formatTimecode(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = String(Math.floor(total / 3600)).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
