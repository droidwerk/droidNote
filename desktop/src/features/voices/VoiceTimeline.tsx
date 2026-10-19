import type { CSSProperties, MouseEvent } from "react";

import type { Segment } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatClock } from "../../shared/lib/format";
import { clusterToken, voiceName, type RosterVoice } from "../../shared/lib/voices";

interface VoiceTimelineProps {
  segments: Segment[];
  roster: RosterVoice[];
  durationMs: number;
  playheadMs?: number | null;
  onSeek?: (ms: number) => void;
}

/** Quem falou quando: uma faixa por voz, como num multitrack. */
export function VoiceTimeline({ segments, roster, durationMs, playheadMs = null, onSeek }: VoiceTimelineProps) {
  const t = useT();
  const lastEnd = segments.reduce((max, item) => Math.max(max, item.end_ms), 0);
  const span = Math.max(durationMs, lastEnd, 1000);
  if (roster.length === 0) return null;
  const ticks = buildTicks(span);

  const seek = (event: MouseEvent<HTMLDivElement>) => {
    if (!onSeek) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    onSeek(Math.round(ratio * span));
  };

  return (
    <div className="timeline" aria-label={t("voices.timeline")}>
      <div className="timeline-head">
        <span className="eyebrow">{t("voices.timeline")}</span>
        <span className="timeline-span">{formatClock(span)}</span>
      </div>
      <div className="timeline-grid">
        {roster.map((voice) => (
          <div className="timeline-row" key={voice.cluster} style={{ "--voice": clusterToken(voice.cluster) } as CSSProperties}>
            <span className="timeline-label">{voice.name ?? voiceName(voice.cluster)}</span>
            <div className={onSeek ? "timeline-lane is-seekable" : "timeline-lane"} onClick={seek}>
              {segments
                .filter((item) => item.speaker_cluster === voice.cluster)
                .map((item) => (
                  <i
                    key={item.id}
                    style={{
                      left: `${(item.start_ms / span) * 100}%`,
                      width: `${Math.max(0.35, ((item.end_ms - item.start_ms) / span) * 100)}%`,
                    }}
                  />
                ))}
              {playheadMs !== null ? <b className="timeline-playhead" style={{ left: `${(playheadMs / span) * 100}%` }} /> : null}
            </div>
          </div>
        ))}
        <div className="timeline-row timeline-axis">
          <span />
          <div className="timeline-ticks">
            {ticks.map((tick) => (
              <small key={tick} style={{ left: `${(tick / span) * 100}%` }}>
                {formatClock(tick)}
              </small>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function buildTicks(span: number): number[] {
  const steps = [10_000, 30_000, 60_000, 120_000, 300_000, 600_000, 900_000, 1_800_000];
  const step = steps.find((item) => span / item <= 6) ?? 3_600_000;
  const ticks: number[] = [];
  for (let value = 0; value <= span; value += step) ticks.push(value);
  return ticks;
}
