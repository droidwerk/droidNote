import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { Person, Segment } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";
import { copyToClipboard, formatClock, highlight } from "../../shared/lib/format";
import { formatPlain, splitScene, groupTurns } from "../../shared/lib/segments";
import { useTheme } from "../../shared/lib/theme";
import { speakerName, voiceToken } from "../../shared/lib/voices";
import { Button } from "../../shared/ui/primitives";

interface SpeakerInfo {
  name: string;
  color: string;
  named: boolean;
  cluster: string | null;
  uncertain: boolean;
}

const UNCERTAIN = 0.42;

function speakerInfo(segment: Segment, people: Person[]): SpeakerInfo {
  const named = Boolean(segment.speaker_id && (people.some((item) => item.id === segment.speaker_id) || segment.speaker_name));
  return {
    name: speakerName(segment, people),
    color: voiceToken(segment),
    named,
    cluster: segment.speaker_cluster ?? null,
    uncertain:
      Boolean(segment.speaker_cluster) &&
      typeof segment.speaker_confidence === "number" &&
      segment.speaker_confidence < UNCERTAIN,
  };
}

export interface SegmentPatch {
  speaker_id?: string | null;
  name?: string;
  text?: string;
  apply_forward?: boolean;
}

interface TranscriptListProps {
  segments: Segment[];
  query: string;
  emptyHint?: string;
  /** Segunda linha do vazio; null esconde (sessão antiga não vai receber trechos). */
  emptyDetail?: string | null;
  people?: Person[];
  languageLocked?: boolean;
  sessionId?: string | null;
  assigningAll?: boolean;
  activeMs?: number | null;
  /** Momento citado (ata, chat): rola até a fala e destaca. */
  focusMs?: number | null;
  receiving?: boolean;
  liveLabel?: string;
  onSeek?: (ms: number) => void;
  onPatchSegment?: (segmentId: string, payload: SegmentPatch) => Promise<void>;
  onAssignAll?: () => Promise<void>;
  onAskSelected?: (segment: Segment) => void;
}

const LAST_SPEAKER_KEY = "droidnote.lastSpeaker";

export function TranscriptList({
  segments,
  query,
  emptyHint,
  emptyDetail,
  people = [],
  languageLocked = false,
  sessionId,
  assigningAll = false,
  activeMs = null,
  focusMs = null,
  receiving = false,
  liveLabel,
  onSeek,
  onPatchSegment,
  onAssignAll,
  onAskSelected,
}: TranscriptListProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState<"all" | string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lastSpeakerId, setLastSpeakerId] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(LAST_SPEAKER_KEY);
    } catch {
      return null;
    }
  });
  const t = useT();
  useTheme();
  // Etiqueta de idioma só quando a conversa mistura idiomas; com um só, é ruído.
  const hideLanguage = languageLocked || new Set(segments.map((item) => item.language).filter(Boolean)).size < 2;

  const stuckToBottom = useRef(true);

  useEffect(() => {
    if (focusMs === null) return undefined;
    const node = scroller.current;
    if (!node) return undefined;
    const rows = [...node.querySelectorAll<HTMLElement>("article[data-start]")];
    const target =
      rows.find((row) => Number(row.dataset.end) >= focusMs && Number(row.dataset.start) <= focusMs + 1500) ??
      rows.find((row) => Number(row.dataset.end) >= focusMs) ??
      rows[rows.length - 1];
    if (!target) return undefined;
    stuckToBottom.current = false;
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.add("is-cited");
    const timer = window.setTimeout(() => target.classList.remove("is-cited"), 1800);
    return () => window.clearTimeout(timer);
  }, [focusMs]);

  useEffect(() => {
    const node = scroller.current;
    if (!node || !stuckToBottom.current || !receiving) return;
    node.scrollTop = node.scrollHeight;
  }, [segments, receiving]);

  const rememberSpeaker = (personId: string | null | undefined) => {
    if (!personId) return;
    setLastSpeakerId(personId);
    try {
      window.localStorage.setItem(LAST_SPEAKER_KEY, personId);
    } catch {
      /* ignore quota */
    }
  };

  const assignSelected = async (payload: SegmentPatch) => {
    if (!selectedId || !onPatchSegment) return;
    if (payload.speaker_id) rememberSpeaker(payload.speaker_id);
    await onPatchSegment(selectedId, payload);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (!selectedId || !onPatchSegment) return;
      if (event.key >= "1" && event.key <= "9") {
        const person = people[Number(event.key) - 1];
        if (!person) return;
        event.preventDefault();
        rememberSpeaker(person.id);
        void onPatchSegment(selectedId, {
          speaker_id: person.id,
          apply_forward: !event.altKey,
        });
      }
      if (event.key === "l" || event.key === "L") {
        if (!lastSpeakerId) return;
        event.preventDefault();
        void onPatchSegment(selectedId, { speaker_id: lastSpeakerId, apply_forward: false });
      }
      if (event.key === "f" || event.key === "F") {
        if (!lastSpeakerId) return;
        event.preventDefault();
        void onPatchSegment(selectedId, { speaker_id: lastSpeakerId, apply_forward: true });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, people, lastSpeakerId, onPatchSegment]);

  const trackScroll = () => {
    const node = scroller.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    stuckToBottom.current = distance < 48;
  };

  const flash = (key: "all" | string) => {
    setCopied(key);
    window.setTimeout(() => setCopied((current) => (current === key ? null : current)), 1400);
  };

  const copyAll = async () => {
    const body = segments
      .map((item) => formatPlain(item, people))
      .join("\n\n");
    if (await copyToClipboard(body)) flash("all");
  };

  const emptyCopy = emptyHint ?? t("transcript.empty");
  const canLabel = Boolean(onPatchSegment);
  const keysActive = canLabel && Boolean(selectedId);

  return (
    <div className={receiving ? "transcript-wrap is-receiving" : "transcript-wrap"}>
      {liveLabel || segments.length > 0 ? (
      <div className="transcript-toolbar">
        <div className="transcript-meta">
          {liveLabel ? <span className="transcript-live">{liveLabel}</span> : null}
        </div>
        <div className="transcript-actions">
          {selectedId && onAskSelected ? (
            <Button
              size="sm"
              variant="quiet"
              onClick={() => {
                const selected = segments.find((item) => item.id === selectedId);
                if (selected) onAskSelected(selected);
              }}
            >
              {t("transcript.ask")}
            </Button>
          ) : null}
          {lastSpeakerId && onPatchSegment && selectedId ? (
            <Button
              size="sm"
              variant="quiet"
              onClick={() => void assignSelected({ speaker_id: lastSpeakerId, apply_forward: true })}
            >
              {t("transcript.fromHere")}
            </Button>
          ) : null}
          {segments.length > 0 ? (
            <Button size="sm" variant="quiet" onClick={() => void copyAll()}>
              {copied === "all" ? t("common.copied") : t("transcript.copyAll")}
            </Button>
          ) : null}
          {onAssignAll && segments.length > 0 ? (
            <Button
              size="sm"
              variant="quiet"
              disabled={assigningAll}
              title={t("transcript.assignTitle")}
              onClick={() => void onAssignAll()}
            >
              {assigningAll ? t("transcript.assigning") : t("transcript.assign")}
            </Button>
          ) : null}
        </div>
      </div>
      ) : null}
      {keysActive ? (
        <p className={keysActive ? "transcript-keys is-active" : "transcript-keys"}>
          {(
            <>
              <span>
                <kbd>1–9</kbd>
                {t("transcript.keysLabel")}
              </span>
              <span>
                <kbd>L</kbd>
                {t("transcript.keysRepeat")}
              </span>
              <span>
                <kbd>F</kbd>
                {t("transcript.keysForward")}
              </span>
            </>
          )}
        </p>
      ) : null}
      <div className="transcript-well">
        {segments.length === 0 ? (
          <div className={receiving ? "transcript-empty is-live" : "transcript-empty"}>
            <span className="transcript-empty-pulse" aria-hidden />
            <div>
              <strong>{emptyCopy}</strong>
              {emptyDetail === null ? null : <p>{emptyDetail ?? t("transcript.emptyHint")}</p>}
            </div>
          </div>
        ) : (
          <div className="transcript" ref={scroller} onScroll={trackScroll}>
        {groupTurns(segments).map((turn) => {
          const head = turn[0];
          if (!head) return null;
          const speaker = speakerInfo(head, people);
          const live = turn.some(
            (segment) =>
              activeMs !== null &&
              activeMs >= segment.start_ms &&
              activeMs < Math.max(segment.end_ms, segment.start_ms + 1),
          );
          const patch =
            onPatchSegment
              ? async (segmentId: string, payload: SegmentPatch) => {
                  if (payload.speaker_id) rememberSpeaker(payload.speaker_id);
                  if (payload.speaker_id !== undefined || payload.name) {
                    for (const item of turn) {
                      await onPatchSegment(item.id, { ...payload, apply_forward: false });
                    }
                    return;
                  }
                  await onPatchSegment(segmentId, payload);
                }
              : undefined;
          if (turn.length === 1) {
            return (
              <SegmentRow
                key={head.id}
                segment={head}
                scene={splitScene(head.text)}
                speaker={speaker}
                continued={false}
                query={query}
                languageLocked={hideLanguage}
                sessionId={sessionId}
                copied={copied === head.id}
                selected={selectedId === head.id}
                live={live}
                people={people}
                lastSpeakerId={lastSpeakerId}
                t={t}
                onSelect={() => setSelectedId(head.id)}
                onSeek={onSeek}
                onPatchSegment={patch}
                onCopied={() => flash(head.id)}
              />
            );
          }
          return (
            <TurnRow
              key={head.id}
              turn={turn}
              speaker={speaker}
              query={query}
              languageLocked={hideLanguage}
              sessionId={sessionId}
              copied={copied === head.id}
              selected={turn.some((item) => item.id === selectedId)}
              live={live}
              people={people}
              lastSpeakerId={lastSpeakerId}
              t={t}
              onSelect={() => setSelectedId(head.id)}
              onSeek={onSeek}
              onPatchSegment={patch}
              onCopied={() => flash(head.id)}
            />
          );
        })}
          </div>
        )}
      </div>
    </div>
  );
}

function TurnRow({
  turn,
  speaker,
  query,
  languageLocked,
  sessionId,
  copied,
  selected,
  live,
  people,
  lastSpeakerId,
  t,
  onSelect,
  onSeek,
  onPatchSegment,
  onCopied,
}: {
  turn: Segment[];
  speaker: SpeakerInfo;
  query: string;
  languageLocked: boolean;
  sessionId?: string | null;
  copied: boolean;
  selected: boolean;
  live: boolean;
  people: Person[];
  lastSpeakerId: string | null;
  t: TranslateFn;
  onSelect: () => void;
  onSeek?: (ms: number) => void;
  onPatchSegment?: (segmentId: string, payload: SegmentPatch) => Promise<void>;
  onCopied: () => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const head = turn[0];
  if (!head) return null;
  const editable = Boolean(onPatchSegment && sessionId);
  const classes = ["segment", "turn"];
  if (selected) classes.push("is-selected");
  if (live) classes.push("is-live");
  const joined = turn.map((item) => splitScene(item.text).body).join(" ");
  const language = turn.find((item) => item.language)?.language;

  return (
    <article
      data-start={turn[0]?.start_ms}
      data-end={turn[turn.length - 1]?.end_ms}
      className={classes.join(" ")}
      style={{ "--chip": speaker.color } as CSSProperties}
      onClick={onSelect}
    >
      <span className="segment-rail" aria-hidden="true" />
      <div className="segment-body">
        <div className="segment-head">
          {onPatchSegment && sessionId ? (
            <SpeakerChip
              speaker={speaker}
              people={people}
              lastSpeakerId={lastSpeakerId}
              t={t}
              onAssign={(payload) => onPatchSegment(head.id, payload)}
            />
          ) : (
            <span className={speaker.named || speaker.cluster ? "speaker-chip" : "speaker-chip empty"}>
              {speaker.name}
            </span>
          )}
          <div className="segment-actions">
            <time
              className={onSeek ? "segment-time is-seekable" : "segment-time"}
              onClick={(event) => {
                if (!onSeek) return;
                event.stopPropagation();
                onSeek(head.start_ms);
              }}
            >
              {formatClock(head.start_ms)}
            </time>
            {!languageLocked && language ? <span className="lang">{language}</span> : null}
            <Button
              size="sm"
              variant="quiet"
              className="segment-action"
              onClick={() => {
                void copyToClipboard(joined).then((ok) => {
                  if (ok) onCopied();
                });
              }}
            >
              {copied ? t("common.copied") : t("common.copy")}
            </Button>
          </div>
        </div>
        <div className="turn-text">
          {turn.map((segment) => (
            <SegmentText
              key={segment.id}
              segmentId={segment.id}
              scene={splitScene(segment.text)}
              query={query}
              editing={editingId === segment.id}
              t={t}
              onStartEdit={() => setEditingId(segment.id)}
              onCancel={() => setEditingId(null)}
              onSave={
                onPatchSegment && editable
                  ? async (text) => {
                      await onPatchSegment(segment.id, { text, apply_forward: false });
                      setEditingId(null);
                    }
                  : undefined
              }
            />
          ))}
        </div>
      </div>
    </article>
  );
}

function SegmentRow({
  segment,
  scene,
  speaker,
  continued,
  query,
  languageLocked,
  sessionId,
  copied,
  selected,
  live,
  people,
  lastSpeakerId,
  t,
  onSelect,
  onSeek,
  onPatchSegment,
  onCopied,
}: {
  segment: Segment;
  scene: { label: string | null; body: string };
  speaker: SpeakerInfo;
  continued: boolean;
  query: string;
  languageLocked: boolean;
  sessionId?: string | null;
  copied: boolean;
  selected: boolean;
  live: boolean;
  people: Person[];
  lastSpeakerId: string | null;
  t: TranslateFn;
  onSelect: () => void;
  onSeek?: (ms: number) => void;
  onPatchSegment?: (segmentId: string, payload: SegmentPatch) => Promise<void>;
  onCopied: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const editable = Boolean(onPatchSegment && sessionId);
  const classes = ["segment"];
  if (continued) classes.push("continued");
  if (selected) classes.push("is-selected");
  if (live) classes.push("is-live");

  return (
    <article
      data-start={segment.start_ms}
      data-end={segment.end_ms}
      className={classes.join(" ")}
      style={{ "--chip": speaker.color } as CSSProperties}
      onClick={onSelect}
    >
      <span className="segment-rail" aria-hidden="true" />
      <div className="segment-body">
        <div className="segment-head">
          {onPatchSegment && sessionId ? (
            <SpeakerChip
              speaker={speaker}
              people={people}
              lastSpeakerId={lastSpeakerId}
              t={t}
              onAssign={(payload) => onPatchSegment(segment.id, payload)}
            />
          ) : (
            <span className={speaker.named || speaker.cluster ? "speaker-chip" : "speaker-chip empty"}>
              {speaker.name}
            </span>
          )}
          <div className="segment-actions">
            <time
              className={onSeek ? "segment-time is-seekable" : "segment-time"}
              onClick={(event) => {
                if (!onSeek) return;
                event.stopPropagation();
                onSeek(segment.start_ms);
              }}
            >
              {formatClock(segment.start_ms)}
            </time>
            {!languageLocked && segment.language ? <span className="lang">{segment.language}</span> : null}
            <Button
              size="sm"
              variant="quiet"
              className="segment-action"
              onClick={() => {
                void copyToClipboard(formatPlain(segment, people)).then((ok) => {
                  if (ok) onCopied();
                });
              }}
            >
              {copied ? t("common.copied") : t("common.copy")}
            </Button>
            {editable ? (
              <Button size="sm" variant="quiet" className="segment-action" onClick={() => setEditing(true)}>
                {t("transcript.edit")}
              </Button>
            ) : null}
          </div>
        </div>
        <SegmentText
          segmentId={segment.id}
          scene={scene}
          query={query}
          editing={editing}
          t={t}
          onStartEdit={() => setEditing(true)}
          onCancel={() => setEditing(false)}
          onSave={
            onPatchSegment
              ? async (text) => {
                  await onPatchSegment(segment.id, { text, apply_forward: false });
                  setEditing(false);
                }
              : undefined
          }
        />
      </div>
    </article>
  );
}

function SegmentText({
  segmentId,
  scene,
  query,
  editing,
  t,
  onSave,
  onCancel,
  onStartEdit,
}: {
  segmentId: string;
  scene: { label: string | null; body: string };
  query: string;
  editing: boolean;
  t: TranslateFn;
  onSave?: (text: string) => Promise<void>;
  onCancel: () => void;
  onStartEdit: () => void;
}) {
  const [draft, setDraft] = useState(scene.body);

  useEffect(() => {
    if (!editing) setDraft(scene.body);
  }, [scene.body, editing]);

  if (editing && onSave) {
    return (
      <div className="segment-edit">
        <textarea
          className="segment-textarea"
          value={draft}
          autoFocus
          rows={Math.min(8, Math.max(3, draft.split("\n").length + 1))}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setDraft(scene.body);
              onCancel();
            }
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              void onSave(draft);
            }
          }}
        />
        <div className="segment-edit-actions">
          <Button size="sm" variant="primary" onClick={() => void onSave(draft)}>
            {t("common.save")}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setDraft(scene.body);
              onCancel();
            }}
          >
            {t("common.cancel")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <p
      className={onSave ? "segment-text editable" : "segment-text"}
      onDoubleClick={() => {
        if (onSave) onStartEdit();
      }}
    >
      {scene.label ? <span className="scene-tag">{scene.label}</span> : null}
      {highlight(scene.body, query).map((part, index) =>
        query && part.toLowerCase() === query.trim().toLowerCase() ? (
          <mark className="mark" key={`${segmentId}-${index}`}>
            {part}
          </mark>
        ) : (
          <span key={`${segmentId}-${index}`}>{part}</span>
        ),
      )}
    </p>
  );
}

function SpeakerChip({
  speaker,
  people,
  lastSpeakerId,
  t,
  onAssign,
}: {
  speaker: SpeakerInfo;
  people: Person[];
  lastSpeakerId: string | null;
  t: TranslateFn;
  onAssign: (payload: { speaker_id?: string | null; name?: string; apply_forward?: boolean }) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [forward, setForward] = useState(true);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const commitNew = async () => {
    const cleaned = name.trim();
    if (!cleaned) return;
    await onAssign({ name: cleaned, apply_forward: forward });
    setName("");
    setOpen(false);
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && buttonRef.current) setRect(buttonRef.current.getBoundingClientRect());
  };

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    document.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  return (
    <div className="speaker-picker">
      <button
        type="button"
        ref={buttonRef}
        className={[
          "speaker-chip",
          speaker.named || speaker.cluster ? "" : "empty",
          speaker.uncertain ? "is-uncertain" : "",
        ].filter(Boolean).join(" ")}
        title={speaker.uncertain ? t("voices.lowConfidence") : undefined}
        onClick={(event) => {
          event.stopPropagation();
          toggle();
        }}
      >
        <span className="speaker-dot" aria-hidden />
        {speaker.name}
      </button>
      {open && rect
        ? createPortal(
            <div
              className="speaker-menu portal"
              ref={menuRef}
              style={{
                top: rect.bottom + 8,
                left: Math.min(rect.left, window.innerWidth - 240),
              }}
            >
              <label className="check-control speaker-forward">
                <input
                  type="checkbox"
                  checked={forward}
                  onChange={(event) => setForward(event.target.checked)}
                />
                <span className="check-box" aria-hidden />
                <span>
                  <strong>{speaker.cluster ? t("voices.applyVoice") : t("transcript.forwardTitle")}</strong>
                  <small>{speaker.cluster ? t("voices.applyVoiceHint") : t("transcript.forwardHint")}</small>
                </span>
              </label>
              {lastSpeakerId
                ? people
                    .filter((person) => person.id === lastSpeakerId)
                    .map((person) => (
                      <button
                        key={`last-${person.id}`}
                        type="button"
                        onClick={() => {
                          void onAssign({ speaker_id: person.id, apply_forward: forward });
                          setOpen(false);
                        }}
                      >
                        {t("transcript.lastSpeaker", { name: person.name })}
                      </button>
                    ))
                : null}
              {people.map((person) => (
                <button
                  key={person.id}
                  type="button"
                  onClick={() => {
                    void onAssign({ speaker_id: person.id, apply_forward: forward });
                    setOpen(false);
                  }}
                >
                  {person.name}
                </button>
              ))}
              {speaker.named ? (
                <button
                  type="button"
                  onClick={() => {
                    void onAssign({ speaker_id: null, apply_forward: false });
                    setOpen(false);
                  }}
                >
                  {t("transcript.noSpeaker")}
                </button>
              ) : null}
              <input
                className="search"
                placeholder={t("transcript.registerName")}
                value={name}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void commitNew();
                  }
                }}
              />
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
