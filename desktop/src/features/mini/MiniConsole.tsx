import { useEffect, useState, type CSSProperties } from "react";

import { api, openTranscriptSocket, setBackend } from "../../shared/api/client";
import type { CaptureState, Person } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { closeMiniWindow, focusMainWindow } from "../../shared/lib/miniWindow";
import { clusterToken, voiceName } from "../../shared/lib/voices";
import { Icon } from "../../shared/ui/Icon";
import { VoicePrint } from "../voices/VoicePrint";

interface LiveVoice {
  cluster: string;
  person_id: string | null;
  name: string | null;
}

/** Janela flutuante durante a gravação: tempo, quem fala, última frase, nota rápida. */
export function MiniConsole() {
  const t = useT();
  const [ready, setReady] = useState(false);
  const [capture, setCapture] = useState<CaptureState | null>(null);
  const [voice, setVoice] = useState<LiveVoice | null>(null);
  const [line, setLine] = useState<{ text: string; cluster: string | null; name: string | null } | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [note, setNote] = useState("");
  const [flash, setFlash] = useState(false);
  const [busy, setBusy] = useState(false);
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
        const segment = event.segment as { text?: string; speaker_cluster?: string | null; speaker_name?: string | null };
        if (segment.text) {
          setLine({ text: segment.text, cluster: segment.speaker_cluster ?? null, name: segment.speaker_name ?? null });
        }
      }
    });
  }, [ready]);

  const recording = Boolean(capture?.recording);
  const sessionId = capture?.session_id ?? null;
  const speaker = voice
    ? people.find((item) => item.id === voice.person_id)?.name ?? voice.name ?? voiceName(voice.cluster)
    : null;

  const saveNote = async () => {
    const text = note.trim();
    if (!text || !sessionId || !recording) return;
    await api.addNote(sessionId, text);
    setNote("");
    setFlash(true);
    window.setTimeout(() => setFlash(false), 900);
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

  return (
    <div className={recording ? "mini is-live" : "mini"}>
      <header className="mini-head" data-tauri-drag-region>
        <span className="state-led" aria-hidden />
        <span className="mini-state" data-tauri-drag-region>
          {recording ? t("status.live") : t("status.standby")}
        </span>
        <span className="mini-clock" data-tauri-drag-region>
          {formatTimecode(elapsed)}
        </span>
        <button type="button" className="mini-icon" title={t("mini.openMain")} onClick={() => void focusMainWindow()}>
          <Icon name="arrow" size={14} />
        </button>
        <button type="button" className="mini-icon" title={t("mini.close")} onClick={() => void closeMiniWindow()}>
          <Icon name="close" size={14} />
        </button>
      </header>
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
          {line ? (
            <>
              {line.name || line.cluster ? <b>{line.name ?? voiceName(line.cluster)}: </b> : null}
              {line.text}
            </>
          ) : (
            <span className="muted">{t("mini.noLine")}</span>
          )}
        </p>
      </div>
      <footer className="mini-foot">
        <input
          className={flash ? "mini-note is-saved" : "mini-note"}
          value={note}
          disabled={!recording}
          placeholder={recording ? t("notes.placeholderLive") : t("mini.noteDisabled")}
          onChange={(event) => setNote(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void saveNote();
            }
          }}
        />
        <button
          type="button"
          className={recording ? "mini-rec is-live" : "mini-rec"}
          disabled={busy}
          title={recording ? t("live.stop") : t("live.start")}
          onClick={() => void toggle()}
        >
          <span className={recording ? "reactor-stop" : "reactor-dot"} />
        </button>
      </footer>
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
