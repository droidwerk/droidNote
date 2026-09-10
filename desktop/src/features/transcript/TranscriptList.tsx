import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { Person, Segment } from "../../shared/api/types";
import { currentUiLanguage, pluralForm, useT } from "../../shared/i18n";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";
import { copyToClipboard, formatClock, highlight } from "../../shared/lib/format";
import { formatPlain, resolveSpeaker, splitScene, groupTurns } from "../../shared/lib/segments";
import { cssVar, useTheme } from "../../shared/lib/theme";
import { Button } from "../../shared/ui/primitives";

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
  people?: Person[];
  languageLocked?: boolean;
  sessionId?: string | null;
  assigningAll?: boolean;
  activeMs?: number | null;
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
  people = [],
  languageLocked = false,
  sessionId,
  assigningAll = false,
  activeMs = null,
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
  const locale = currentUiLanguage();
  useTheme();

  const stuckToBottom = useRef(true);

  useEffect(() => {
    const node = scroller.current;
    if (!node || !stuckToBottom.current) return;
    node.scrollTop = node.scrollHeight;
  }, [segments]);

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
      <div className="transcript-toolbar">
        <div className="transcript-meta">
          {liveLabel ? <span className="transcript-live">{liveLabel}</span> : null}
          <span className="transcript-count">
            {t(`transcript.${pluralForm(locale, segments.length)}`, { count: segments.length })}
          </span>
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
      {canLabel ? (
        <p className={keysActive ? "transcript-keys is-active" : "transcript-keys"}>
          {keysActive ? (
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
          ) : (
            <span>{t("transcript.keysIdle")}</span>
          )}
        </p>
      ) : null}
      <div className="transcript-well">
        {segments.length === 0 ? (
          <div className={receiving ? "transcript-empty is-live" : "transcript-empty"}>
            <span className="transcript-empty-pulse" aria-hidden />
            <div>
              <strong>{emptyCopy}</strong>
              <p>{t("transcript.emptyHint")}</p>
            </div>
          </div>
        ) : (
          <div className="transcript" ref={scroller} onScroll={trackScroll}>
        {groupTurns(segments).map((turn) => {
          const head = turn[0];
          if (!head) return null;
          const speaker = resolveSpeaker(head, people);
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
                languageLocked={languageLocked}
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
              languageLocked={languageLocked}
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
  speaker: Person | null;
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
      className={classes.join(" ")}
      style={{ "--chip": speaker ? speakerColor(speaker.id) : "var(--border)" } as CSSProperties}
      onClick={onSelect}
    >
      <span className="segment-rail" aria-hidden="true" />
      <div className="segment-body">
        <div className="segment-head">
          {onPatchSegment && sessionId ? (
            <SpeakerChip
              speaker={speaker}
              source={head.source}
              people={people}
              lastSpeakerId={lastSpeakerId}
              t={t}
              onAssign={(payload) => onPatchSegment(head.id, payload)}
            />
          ) : speaker ? (
            <span className="speaker-chip" style={{ "--chip": speakerColor(speaker.id) } as CSSProperties}>
              {speaker.name}
            </span>
          ) : (
            <span className="speaker-chip empty">{sourceLabel(head.source, t)}</span>
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
  speaker: Person | null;
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
      className={classes.join(" ")}
      style={{ "--chip": speaker ? speakerColor(speaker.id) : "var(--border)" } as CSSProperties}
      onClick={onSelect}
    >
      <span className="segment-rail" aria-hidden="true" />
      <div className="segment-body">
        <div className="segment-head">
          {onPatchSegment && sessionId ? (
            <SpeakerChip
              speaker={speaker}
              source={segment.source}
              people={people}
              lastSpeakerId={lastSpeakerId}
              t={t}
              onAssign={(payload) => onPatchSegment(segment.id, payload)}
            />
          ) : speaker ? (
            <span className="speaker-chip" style={{ "--chip": speakerColor(speaker.id) } as CSSProperties}>
              {speaker.name}
            </span>
          ) : (
            <span className="speaker-chip empty">{sourceLabel(segment.source, t)}</span>
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
                Editar
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
  source,
  people,
  lastSpeakerId,
  t,
  onAssign,
}: {
  speaker: Person | null;
  source?: string | null;
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
        className={speaker ? "speaker-chip" : "speaker-chip empty"}
        style={speaker ? ({ "--chip": speakerColor(speaker.id) } as CSSProperties) : undefined}
        onClick={(event) => {
          event.stopPropagation();
          toggle();
        }}
      >
        {speaker ? speaker.name : sourceLabel(source, t)}
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
                  <strong>{t("transcript.forwardTitle")}</strong>
                  <small>{t("transcript.forwardHint")}</small>
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
              {speaker ? (
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

function sourceLabel(source: string | null | undefined, t: TranslateFn): string {
  if (source === "mic") return t("common.you");
  if (source === "loopback") return t("common.others");
  return t("common.whoSpoke");
}

function speakerColor(id: string): string {
  const colors = [
    cssVar("--ink-1", "#ff6a14"),
    cssVar("--ink-2", "#3dd68c"),
    cssVar("--ink-3", "#6ea8ff"),
    cssVar("--ink-4", "#f59e0b"),
    cssVar("--ink-5", "#c084fc"),
    cssVar("--ink-6", "#ff6b6b"),
  ];
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) | 0;
  }
  return colors[Math.abs(hash) % colors.length] ?? colors[0] ?? "#ff6a14";
}
