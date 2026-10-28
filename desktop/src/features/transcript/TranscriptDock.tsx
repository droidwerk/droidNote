import { useCallback, useState, type CSSProperties } from "react";

import type { Person, Segment } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatClock } from "../../shared/lib/format";
import { clusterToken, voiceName } from "../../shared/lib/voices";
import { Icon } from "../../shared/ui/Icon";

const KEY = "droidnote.transcriptDock";

/** A transcrição fica num canto; recolhida, vira uma faixa com as últimas falas. */
export function useTranscriptDock(): [boolean, () => void] {
  const [min, setMin] = useState(() => {
    try {
      return window.localStorage.getItem(KEY) === "min";
    } catch {
      return false;
    }
  });
  const toggle = useCallback(() => {
    setMin((value) => {
      const next = !value;
      try {
        window.localStorage.setItem(KEY, next ? "min" : "open");
      } catch {
        /* só conveniência */
      }
      return next;
    });
  }, []);
  return [min, toggle];
}

export function DockToggle({ min, onToggle }: { min: boolean; onToggle: () => void }) {
  const t = useT();
  const label = min ? t("dock.expand") : t("dock.collapse");
  return (
    <button type="button" className="dock-toggle" onClick={onToggle} title={label} aria-label={label} aria-expanded={!min}>
      <Icon name={min ? "expand" : "collapse"} size={14} />
    </button>
  );
}

export function TranscriptTicker({
  segments,
  people,
  live,
  onExpand,
}: {
  segments: Segment[];
  people: Person[];
  live: boolean;
  onExpand: () => void;
}) {
  const t = useT();
  const tail = segments.slice(-3);
  if (!tail.length) {
    return <p className="ticker-empty">{live ? t("live.listening") : t("transcript.emptyPast")}</p>;
  }
  return (
    <button type="button" className={live ? "ticker is-live" : "ticker"} onClick={onExpand} title={t("dock.expand")}>
      {tail.map((segment) => {
        const name =
          people.find((item) => item.id === segment.speaker_id)?.name ??
          segment.speaker_name ??
          (segment.speaker_cluster ? voiceName(segment.speaker_cluster) : "");
        const color = segment.speaker_cluster ? clusterToken(segment.speaker_cluster) : "var(--muted)";
        return (
          <span key={segment.id} className="ticker-line" style={{ "--voice": color } as CSSProperties}>
            <b>
              {name}
              <small>{formatClock(segment.start_ms)}</small>
            </b>
            <span>{segment.text}</span>
          </span>
        );
      })}
    </button>
  );
}
