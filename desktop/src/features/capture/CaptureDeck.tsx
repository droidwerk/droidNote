import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import type { ChannelLevel, MonitorFrame, Person } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";
import { clusterToken, voiceName } from "../../shared/lib/voices";
import { Icon } from "../../shared/ui/Icon";
import { VoicePrint } from "../voices/VoicePrint";
import { ChannelScope, toLevel } from "./ChannelScope";

type Visual = "idle" | "loading" | "listening" | "transcribing" | "stale";

interface CaptureDeckProps {
  recording: boolean;
  pending: "start" | "stop" | null;
  busy: boolean;
  phase: string;
  elapsedMs: number;
  socketLive: boolean;
  stale: boolean;
  monitor: MonitorFrame | null;
  asrBusy: boolean;
  asrQueued: number;
  micOnly: boolean;
  people: Person[];
  onToggle: () => void;
  toolbar?: ReactNode;
}

export function CaptureDeck({
  recording,
  pending,
  busy,
  phase,
  elapsedMs,
  socketLive,
  stale,
  monitor,
  asrBusy,
  asrQueued,
  micOnly,
  people,
  onToggle,
  toolbar,
}: CaptureDeckProps) {
  const t = useT();
  const working = useHeld(asrBusy || asrQueued > 0);
  const [tick, setTick] = useState(0);
  useEffect(() => setTick((value) => value + 1), [monitor]);

  const visual = visualState({ recording, phase, busy: working, stale, socketLive, loaded: monitor?.whisper_loaded });
  const mic: ChannelLevel | null = monitor?.channels?.mic ?? (monitor ? { rms: monitor.rms, speech: monitor.speech } : null);
  const system = monitor?.channels?.system ?? null;
  const voice = recording ? monitor?.voice ?? null : null;
  const voiceFresh = Boolean(voice);
  const person = voice?.person_id ? people.find((item) => item.id === voice.person_id) : undefined;
  const voiceSeed = voice?.cluster ?? voice?.person_id ?? "known";
  const label =
    pending === "start" ? t("live.starting") : pending === "stop" ? t("live.stopping") : recording ? t("live.stop") : t("live.start");

  return (
    <section className={`deck panel deck-${visual}`} aria-label={t("live.title")}>
      <div className="deck-core">
        <button
          type="button"
          className={["reactor", recording ? "is-live" : "", pending ? "is-pending" : ""].filter(Boolean).join(" ")}
          disabled={busy}
          onClick={onToggle}
          aria-pressed={recording}
          aria-label={label}
          title={`${label} (Ctrl+Shift+R)`}
        >
          <span className="reactor-orbit" aria-hidden />
          <span className="reactor-ring" aria-hidden />
          <span className="reactor-core" aria-hidden>
            <span className={recording ? "reactor-stop" : "reactor-dot"} />
          </span>
        </button>
        <div className="deck-readout">
          <span className="eyebrow">
            <span className={`state-led led-${visual}`} aria-hidden />
            {statusCopy(visual, t)}
            {asrQueued > 0 ? <em>· {t("console.queue", { count: asrQueued })}</em> : null}
          </span>
          <p className={recording ? "timecode is-live" : "timecode"}>{formatTimecode(elapsedMs)}</p>
        </div>
      </div>

      <div className="deck-channels">
        <ChannelStrip
          tone="mic"
          title={t("console.channelMic")}
          icon="mic"
          level={mic?.rms ?? null}
          speech={Boolean(mic?.speech)}
          echo={recording && !micOnly ? Number(mic?.echo ?? 0) : 0}
          gainDb={recording ? Number(mic?.gain_db ?? 0) : 0}
          active={recording}
          enabled
          tick={tick}
          t={t}
        />
        <ChannelStrip
          tone="system"
          title={t("console.channelSystem")}
          icon="system"
          level={system?.rms ?? null}
          speech={Boolean(system?.speech)}
          active={recording && !micOnly}
          enabled={!micOnly}
          tick={tick}
          t={t}
        />
      </div>

      {recording ? (
      <div className={voiceFresh ? "deck-now is-on" : "deck-now"} aria-live="polite">
        <span className="eyebrow">{t("voices.speakingNow")}</span>
        {voice && voiceFresh ? (
          <span className="deck-now-voice" style={{ "--voice": clusterToken(voiceSeed) } as CSSProperties}>
            <VoicePrint seed={voiceSeed} color={clusterToken(voiceSeed)} active />
            <strong>{person?.name ?? voice.name ?? voiceName(voice.cluster)}</strong>
          </span>
        ) : (
          <span className="deck-now-idle">—</span>
        )}
      </div>
      ) : null}
      {toolbar ? <div className="deck-toolbar">{toolbar}</div> : null}
    </section>
  );
}

function ChannelStrip({
  tone,
  title,
  icon,
  level,
  speech,
  echo = 0,
  gainDb = 0,
  active,
  enabled,
  tick,
  t,
}: {
  tone: "mic" | "system";
  title: string;
  icon: "mic" | "system";
  level: number | null;
  speech: boolean;
  echo?: number;
  gainDb?: number;
  active: boolean;
  enabled: boolean;
  tick: number;
  t: TranslateFn;
}) {
  const meter = active && level !== null ? toLevel(level) : 0;
  const state = !enabled ? t("console.off") : !active ? "—" : speech ? t("console.speech") : t("console.silence");
  return (
    <div className={["channel", `channel-${tone}`, speech && active ? "is-speech" : "", enabled ? "" : "is-off"].filter(Boolean).join(" ")}>
      <div className="channel-head">
        <span className="channel-id">
          <Icon name={icon} size={14} />
          {title}
        </span>
        <span className="channel-state">{state}</span>
      </div>
      <ChannelScope rms={active ? level : null} speech={speech} tick={tick} active={active} tone={tone} />
      <div className="channel-foot">
        <span className="channel-meter" aria-hidden>
          <span style={{ width: `${meter * 100}%` }} />
        </span>
        {gainDb >= 1 ? (
          <em className="channel-gain" title={t("gain.badgeHint")}>
            {t("gain.badge", { db: Math.round(gainDb) })}
          </em>
        ) : null}
        {echo > 0.05 ? <em className="channel-echo">{t("console.echo", { pct: Math.round(echo * 100) })}</em> : null}
      </div>
    </div>
  );
}

function useHeld(busy: boolean): boolean {
  const [held, setHeld] = useState(busy);
  useEffect(() => {
    if (busy) {
      setHeld(true);
      return undefined;
    }
    const timer = window.setTimeout(() => setHeld(false), 450);
    return () => window.clearTimeout(timer);
  }, [busy]);
  return held;
}

function visualState(input: {
  recording: boolean;
  phase: string;
  busy: boolean;
  stale: boolean;
  socketLive: boolean;
  loaded?: boolean;
}): Visual {
  if (input.stale || (input.recording && !input.socketLive)) return "stale";
  if (!input.recording) return input.busy ? "transcribing" : "idle";
  if (input.phase === "loading" || input.loaded === false) return "loading";
  if (input.busy) return "transcribing";
  return "listening";
}

function statusCopy(visual: Visual, t: TranslateFn): string {
  if (visual === "stale") return t("meter.stale");
  if (visual === "loading") return t("meter.loading");
  if (visual === "transcribing") return t("meter.transcribing");
  if (visual === "listening") return t("meter.listening");
  return t("console.ready");
}

function formatTimecode(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}
