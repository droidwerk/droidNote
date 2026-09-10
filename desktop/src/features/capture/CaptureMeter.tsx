import { useEffect, useState } from "react";

import { useT } from "../../shared/i18n";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";

interface CaptureMeterProps {
  recording: boolean;
  phase: string;
  elapsedMs: number;
  socketLive: boolean;
  stale: boolean;
  monitor: {
    rms: number;
    speech: boolean;
    bars: number[];
    queued: number;
    buffer_ms: number;
    whisper_loaded: boolean;
  } | null;
  asrBusy: boolean;
  asrQueued?: number;
}

export function CaptureMeter({
  recording,
  phase,
  elapsedMs,
  socketLive,
  stale,
  monitor,
  asrBusy,
  asrQueued = 0,
}: CaptureMeterProps) {
  const t = useT();
  const busy = useHeldBusy(asrBusy || asrQueued > 0);
  const bars = normalizeBars(monitor?.bars);
  const visual = visualState({ recording, phase, busy, stale, socketLive, loaded: monitor?.whisper_loaded });
  const status = statusCopy(visual, t);

  return (
    <section className={`meter meter-${visual}`}>
      <div className="meter-time">
        <span className="meter-state-dot" aria-hidden />
        <p className={recording ? "meter-clock live" : "meter-clock"}>{formatElapsed(elapsedMs)}</p>
      </div>
      <div className="vu" aria-hidden="true">
        {bars.map((value, index) => (
          <span
            key={index}
            className={value > 0.1 ? "is-active" : ""}
            style={{ height: `${barHeight(value, index, recording && !monitor)}%` }}
          />
        ))}
      </div>
      <p className="meter-status" aria-live="polite">
        {status}
      </p>
    </section>
  );
}

function useHeldBusy(busy: boolean): boolean {
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
}): "idle" | "loading" | "listening" | "transcribing" | "stale" {
  if (input.stale || (input.recording && !input.socketLive)) return "stale";
  if (!input.recording) {
    return input.busy ? "transcribing" : "idle";
  }
  if (input.phase === "loading" || input.loaded === false) return "loading";
  if (input.busy) return "transcribing";
  return "listening";
}

function statusCopy(visual: ReturnType<typeof visualState>, t: TranslateFn): string {
  if (visual === "stale") return t("meter.stale");
  if (visual === "loading") return t("meter.loading");
  if (visual === "transcribing") return t("meter.transcribing");
  if (visual === "listening") return t("meter.listening");
  return t("meter.ready");
}

function normalizeBars(values?: number[]): number[] {
  return Array.from({ length: 16 }, (_, index) => {
    const value = values?.[index];
    return typeof value === "number" && Number.isFinite(value)
      ? Math.max(0, Math.min(1, value))
      : 0;
  });
}

function barHeight(value: number, index: number, waiting: boolean): number {
  if (waiting) return 10 + ((index * 7) % 18);
  return Math.max(4, Math.min(100, value * 100));
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}
