import { useEffect, useRef, useState, type CSSProperties } from "react";

import { api, askChat, openTranscriptSocket, setBackend } from "../../shared/api/client";
import type { Brief, CaptureState, Person } from "../../shared/api/types";
import { useI18n } from "../../shared/i18n";
import { closeMiniWindow, focusMainWindow, resizeMiniWindow } from "../../shared/lib/miniWindow";
import { clusterToken, voiceName } from "../../shared/lib/voices";
import { AiThinking } from "../../shared/ui/AiThinking";
import { Icon, type IconName } from "../../shared/ui/Icon";
import { copyConsent } from "../consent/consent";
import { VoicePrint } from "../voices/VoicePrint";

interface LiveVoice {
  cluster: string;
  person_id: string | null;
  name: string | null;
}

interface Line {
  id: string;
  text: string;
  cluster: string | null;
  name: string | null;
}

type Pane = "live" | "ask" | "context";
type Marker = "decision" | "task" | "important" | "question";

const MARKERS: { id: Marker; icon: IconName }[] = [
  { id: "decision", icon: "check" },
  { id: "task", icon: "tasks" },
  { id: "important", icon: "spark" },
  { id: "question", icon: "chat" },
];
const QUICK_ASKS = ["sofar", "decided", "missed", "suggest"] as const;
const TAIL = 8;
const EXPANDED_KEY = "droidnote.miniExpanded";

/** Janela flutuante: acompanha a reunião, marca momentos e pergunta à IA sem sair da chamada. */
export function MiniConsole() {
  const { t, locale } = useI18n();
  const [ready, setReady] = useState(false);
  const [capture, setCapture] = useState<CaptureState | null>(null);
  const [voice, setVoice] = useState<LiveVoice | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [note, setNote] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(() => readFlag(EXPANDED_KEY));
  const [pane, setPane] = useState<Pane>("live");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const tail = useRef<HTMLOListElement>(null);
  const elapsed = useElapsed(capture?.recording ? capture.started_at ?? null : null);

  useEffect(() => {
    document.documentElement.classList.add("is-mini");
    let cancelled = false;
    void (async () => {
      if ("__TAURI_INTERNALS__" in window) {
        const { invoke } = await import("@tauri-apps/api/core");
        setBackend(await invoke<{ url: string; token: string }>("get_backend"));
      }
      if (cancelled) return;
      try {
        setCapture(await api.captureState());
        setPeople(await api.people());
      } catch {
        /* backend ainda subindo */
      }
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    void resizeMiniWindow(expanded).catch(() => undefined);
    writeFlag(EXPANDED_KEY, expanded);
  }, [expanded]);

  useEffect(() => {
    if (!ready) return undefined;
    return openTranscriptSocket((event) => {
      if (event.type === "capture" || event.type === "hello") {
        setCapture((current) => ({
          ...(current ?? { mic_only: false, warning: null }),
          recording: Boolean(event.recording),
          session_id: typeof event.session_id === "string" ? event.session_id : current?.session_id ?? null,
          started_at: typeof event.started_at === "string" ? event.started_at : null,
        }) as CaptureState);
        if (!event.recording) setVoice(null);
      }
      if (event.type === "monitor") {
        const raw = event.voice as LiveVoice | null | undefined;
        setVoice(raw && typeof raw.cluster === "string" ? raw : null);
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
  const sessionId = capture?.session_id ?? null;

  useEffect(() => {
    if (!sessionId) {
      setBrief(null);
      return;
    }
    setLines([]);
    setAnswer("");
    setChatId(null);
    void api.brief({ sessionId }).then(setBrief).catch(() => setBrief(null));
  }, [sessionId]);

  useEffect(() => {
    tail.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [lines, expanded, pane]);

  const nameOf = (cluster: string | null, name: string | null, personId?: string | null) =>
    people.find((item) => item.id === personId)?.name ?? name ?? (cluster ? voiceName(cluster) : "");
  const speaker = voice ? nameOf(voice.cluster, voice.name, voice.person_id) : null;
  const last = lines[lines.length - 1] ?? null;

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

  const toggle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      setCapture(recording ? await api.stopCapture() : await api.startCapture({ capture_mode: "meeting" }));
    } finally {
      setBusy(false);
    }
  };

  const consent = async () => {
    if (await copyConsent(t)) blink("consent");
  };

  return (
    <div className={["mini", recording ? "is-live" : "", expanded ? "is-expanded" : ""].filter(Boolean).join(" ")}>
      <header className="mini-head" data-tauri-drag-region>
        <span className="state-led" aria-hidden />
        <span className="mini-state" data-tauri-drag-region>
          {recording ? t("status.live") : t("status.standby")}
        </span>
        <span className="mini-clock" data-tauri-drag-region>
          {formatTimecode(elapsed)}
        </span>
        <button
          type="button"
          className={flash === "consent" ? "mini-icon is-done" : "mini-icon"}
          title={t("consent.copyHint")}
          aria-label={t("consent.copyHint")}
          onClick={() => void consent()}
        >
          <Icon name={flash === "consent" ? "check" : "shield"} size={14} />
        </button>
        <button
          type="button"
          className="mini-icon"
          title={expanded ? t("mini.collapse") : t("mini.expand")}
          aria-label={expanded ? t("mini.collapse") : t("mini.expand")}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <Icon name={expanded ? "collapse" : "expand"} size={14} />
        </button>
        <button type="button" className="mini-icon" title={t("mini.openMain")} aria-label={t("mini.openMain")} onClick={() => void focusMainWindow()}>
          <Icon name="arrow" size={14} />
        </button>
        <button type="button" className="mini-icon" title={t("mini.close")} aria-label={t("mini.close")} onClick={() => void closeMiniWindow()}>
          <Icon name="close" size={14} />
        </button>
      </header>

      {expanded ? (
        <>
          <nav className="mini-tabs" role="tablist">
            {(["live", "ask", "context"] as const).map((id) => (
              <button key={id} type="button" role="tab" aria-selected={pane === id} className={pane === id ? "is-on" : ""} onClick={() => setPane(id)}>
                {t(`mini.pane_${id}`)}
                {id === "context" && brief?.pending.length ? <span className="tab-count">{brief.pending.length}</span> : null}
              </button>
            ))}
          </nav>
          <div className="mini-pane">
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
                <p className="mini-empty">{recording ? t("mini.listening") : t("mini.noLine")}</p>
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
                {asking && !answer ? (
                  <AiThinking compact lines={3} steps={[t("ai.listenBack"), t("ai.answer")]} />
                ) : null}
                {answer ? (
                  <div className="mini-answer" aria-live="polite">
                    {answer}
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
        </>
      ) : (
        <div className="mini-body">
          {speaker && voice ? (
            <span className="mini-voice" style={{ "--voice": clusterToken(voice.cluster) } as CSSProperties}>
              <VoicePrint seed={voice.cluster} color={clusterToken(voice.cluster)} active size="sm" />
              <strong>{speaker}</strong>
            </span>
          ) : (
            <span className="mini-voice is-idle">{recording ? t("mini.listening") : t("console.ready")}</span>
          )}
          <p className="mini-line">
            {last ? (
              <>
                {last.name || last.cluster ? <b>{nameOf(last.cluster, last.name)}: </b> : null}
                {last.text}
              </>
            ) : (
              <span className="muted">{t("mini.noLine")}</span>
            )}
          </p>
        </div>
      )}

      <div className="mini-markers" role="group" aria-label={t("mini.markersAria")}>
        {MARKERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={flash === item.id ? "mini-marker is-done" : "mini-marker"}
            disabled={!recording}
            title={t(`mini.markerHint_${item.id}`)}
            onClick={() => void mark(item.id)}
          >
            <Icon name={flash === item.id ? "check" : item.icon} size={12} />
            {t(`mini.marker_${item.id}`)}
          </button>
        ))}
      </div>
      <footer className="mini-foot">
        <input
          className={flash === "note" ? "mini-note is-saved" : "mini-note"}
          value={note}
          disabled={!recording}
          placeholder={recording ? t("notes.placeholderLive") : t("mini.noteDisabled")}
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
        <button
          type="button"
          className={recording ? "mini-rec is-live" : "mini-rec"}
          disabled={busy}
          title={recording ? t("live.stop") : t("live.start")}
          aria-label={recording ? t("live.stop") : t("live.start")}
          onClick={() => void toggle()}
        >
          <span className={recording ? "reactor-stop" : "reactor-dot"} />
        </button>
      </footer>
    </div>
  );
}

function readFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeFlag(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    /* só conveniência */
  }
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
