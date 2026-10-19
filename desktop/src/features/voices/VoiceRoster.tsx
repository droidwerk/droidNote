import { useEffect, useRef, useState, type CSSProperties } from "react";

import type { Person } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatClock } from "../../shared/lib/format";
import { clusterToken, voiceName, type RosterVoice } from "../../shared/lib/voices";
import { Icon } from "../../shared/ui/Icon";
import { VoicePrint } from "./VoicePrint";

interface VoiceRosterProps {
  roster: RosterVoice[];
  people: Person[];
  engineReady: boolean;
  speakingCluster?: string | null;
  refining?: boolean;
  onAssign?: (cluster: string, payload: { person_id?: string | null; name?: string }) => Promise<void>;
  onRefine?: () => void;
  onFocusVoice?: (voice: RosterVoice) => void;
  onDownloadEngine?: () => void;
  engineBusy?: boolean;
}

export function VoiceRoster({
  roster,
  people,
  engineReady,
  speakingCluster,
  refining = false,
  onAssign,
  onRefine,
  onFocusVoice,
  onDownloadEngine,
  engineBusy = false,
}: VoiceRosterProps) {
  const t = useT();
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div className="roster">
      {!engineReady ? (
        <div className="roster-engine">
          <Icon name="voice" />
          <div>
            <strong>{t("voices.engineOff")}</strong>
            <p>{t("voices.engineOffHint")}</p>
            {onDownloadEngine ? (
              <button type="button" className="button button-primary button-sm" disabled={engineBusy} onClick={onDownloadEngine}>
                {engineBusy ? t("voices.downloading") : t("voices.download")}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {roster.length === 0 ? (
        engineReady ? <p className="roster-empty">{t("voices.none")}</p> : null
      ) : (
        <ul className="roster-list">
          {roster.map((voice) => {
            const color = clusterToken(voice.cluster);
            const speaking = speakingCluster === voice.cluster;
            return (
              <li
                key={voice.cluster}
                className={speaking ? "roster-item is-speaking" : "roster-item"}
                style={{ "--voice": color } as CSSProperties}
              >
                <button
                  type="button"
                  className="roster-main"
                  onClick={() => onFocusVoice?.(voice)}
                  title={voice.hasVoiceprint ? t("voices.learned") : undefined}
                >
                  <VoicePrint seed={voice.cluster} color={color} active={speaking} />
                  <span className="roster-copy">
                    <strong>
                      {voice.name ?? voiceName(voice.cluster)}
                      {voice.hasVoiceprint ? <span className="roster-known" aria-label={t("voices.learned")} /> : null}
                    </strong>
                    <small>
                      {voice.name ? `${voiceName(voice.cluster)} · ` : ""}
                      {t("voices.turns", { count: voice.turns })}
                      {voice.sources.includes("mic") ? " · MIC" : ""}
                      {voice.sources.includes("loopback") ? " · SYS" : ""}
                    </small>
                  </span>
                  <span className="roster-share">
                    <b>{Math.round(voice.share * 100)}%</b>
                    <small>{formatClock(voice.talkMs)}</small>
                  </span>
                </button>
                <span className="roster-bar" aria-hidden>
                  <span style={{ width: `${Math.max(2, voice.share * 100)}%` }} />
                </span>
                {onAssign ? (
                  editing === voice.cluster ? (
                    <VoiceNamer
                      people={people}
                      current={voice.personId}
                      onCancel={() => setEditing(null)}
                      onPick={async (payload) => {
                        await onAssign(voice.cluster, payload);
                        setEditing(null);
                      }}
                    />
                  ) : (
                    <button type="button" className="roster-name-btn" onClick={() => setEditing(voice.cluster)}>
                      {voice.name ? t("voices.rename") : t("voices.name")}
                    </button>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {onRefine && engineReady && roster.length > 0 ? (
        <button type="button" className="roster-refine" disabled={refining} onClick={onRefine}>
          <Icon name="refresh" size={14} />
          {refining ? t("voices.refining") : t("voices.refine")}
        </button>
      ) : null}
    </div>
  );
}

function VoiceNamer({
  people,
  current,
  onPick,
  onCancel,
}: {
  people: Person[];
  current: string | null;
  onPick: (payload: { person_id?: string | null; name?: string }) => Promise<void>;
  onCancel: () => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  const cleaned = draft.trim().toLowerCase();
  const matches = people.filter((person) => !cleaned || person.name.toLowerCase().includes(cleaned)).slice(0, 6);

  const pick = async (payload: { person_id?: string | null; name?: string }) => {
    if (busy) return;
    setBusy(true);
    try {
      await onPick(payload);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="namer" onKeyDown={(event) => event.key === "Escape" && onCancel()}>
      <input
        ref={input}
        className="input"
        value={draft}
        placeholder={t("voices.namePlaceholder")}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          const exact = people.find((person) => person.name.toLowerCase() === cleaned);
          if (exact) void pick({ person_id: exact.id });
          else if (draft.trim()) void pick({ name: draft.trim() });
        }}
      />
      <div className="namer-options">
        {matches.map((person) => (
          <button
            key={person.id}
            type="button"
            className={person.id === current ? "namer-chip is-current" : "namer-chip"}
            disabled={busy}
            onClick={() => void pick({ person_id: person.id })}
          >
            {person.name}
          </button>
        ))}
        {draft.trim() && !people.some((person) => person.name.toLowerCase() === cleaned) ? (
          <button type="button" className="namer-chip is-new" disabled={busy} onClick={() => void pick({ name: draft.trim() })}>
            <Icon name="plus" size={12} /> {draft.trim()}
          </button>
        ) : null}
        {current ? (
          <button type="button" className="namer-chip is-clear" disabled={busy} onClick={() => void pick({ person_id: null })}>
            {t("voices.unassign")}
          </button>
        ) : null}
      </div>
      <p className="namer-hint">{t("voices.applyVoiceHint")}</p>
    </div>
  );
}
