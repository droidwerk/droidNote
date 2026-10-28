import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../shared/api/client";
import type { NoteKind, UserNote } from "../../shared/api/types";
import { useI18n } from "../../shared/i18n";
import { formatClock } from "../../shared/lib/format";
import { AiThinking } from "../../shared/ui/AiThinking";
import { InfoTip } from "../../shared/ui/InfoTip";
import { Icon, type IconName } from "../../shared/ui/Icon";
import { useToast } from "../../shared/ui/Toast";

interface UserNotesProps {
  sessionId: string;
  recording: boolean;
  /** Momento atual (reprodução da sessão); sem ele, o servidor usa o instante da gravação. */
  momentMs?: number | null;
  revision?: number;
  onSeek?: (ms: number) => void;
  /** Leva a anotação para o chat como pergunta. */
  onAsk?: (text: string) => void;
  onTasksChanged?: () => void;
}

const KINDS: { id: NoteKind; icon: IconName }[] = [
  { id: "decision", icon: "check" },
  { id: "task", icon: "tasks" },
  { id: "important", icon: "spark" },
  { id: "question", icon: "chat" },
];

type Filter = "all" | NoteKind;

interface Suggestion {
  noteId: string;
  text: string | null;
  error: string | null;
}

/** Suas anotações: presas ao momento da fala, com tipo, e a IA ajudando em cada uma. */
export function UserNotes({ sessionId, recording, momentMs = null, revision = 0, onSeek, onAsk, onTasksChanged }: UserNotesProps) {
  const { t, locale } = useI18n();
  const toast = useToast();
  const [notes, setNotes] = useState<UserNote[]>([]);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<NoteKind | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [tasked, setTasked] = useState<Set<string>>(new Set());
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLOListElement>(null);

  const load = useCallback(async () => {
    try {
      setNotes(await api.notes(sessionId));
    } catch {
      setNotes([]);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  useEffect(() => {
    if (recording) window.setTimeout(() => input.current?.focus(), 30);
  }, [recording]);

  const add = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const note = await api.addNote(sessionId, text, recording ? null : momentMs, kind);
      setNotes((current) => [...current, note].sort((a, b) => a.at_ms - b.at_ms));
      setDraft("");
      window.setTimeout(() => list.current?.lastElementChild?.scrollIntoView({ block: "nearest" }), 20);
    } finally {
      setBusy(false);
    }
  };

  const save = async (note: UserNote) => {
    const text = editDraft.trim();
    setEditing(null);
    if (!text || text === note.text) return;
    setNotes(await api.updateNote(sessionId, note.id, { text }));
  };

  const retag = async (note: UserNote, next: NoteKind | null) => {
    setNotes((current) => current.map((item) => (item.id === note.id ? { ...item, kind: next } : item)));
    setNotes(await api.updateNote(sessionId, note.id, { kind: next }));
  };

  const remove = async (note: UserNote) => {
    await api.deleteNote(sessionId, note.id);
    setNotes((current) => current.filter((item) => item.id !== note.id));
  };

  const expand = async (note: UserNote) => {
    setSuggestion({ noteId: note.id, text: null, error: null });
    try {
      const result = await api.expandNote(sessionId, note.id, locale);
      setSuggestion({ noteId: note.id, text: result.text, error: null });
    } catch (err) {
      setSuggestion({ noteId: note.id, text: null, error: err instanceof Error ? err.message : t("notes.expandFail") });
    }
  };

  const applySuggestion = async (note: UserNote, mode: "replace" | "append") => {
    if (!suggestion?.text) return;
    const text = mode === "replace" ? suggestion.text : `${note.text}\n${suggestion.text}`;
    setSuggestion(null);
    setNotes(await api.updateNote(sessionId, note.id, { text }));
  };

  const toTask = async (note: UserNote) => {
    await api.createTask({ text: (note.text.split("\n")[0] ?? note.text).slice(0, 500), session_id: sessionId });
    setTasked((current) => new Set(current).add(note.id));
    if (note.kind !== "task") void retag(note, "task");
    onTasksChanged?.();
    toast.push({ tone: "success", title: t("notes.taskCreated") });
  };

  const counts = KINDS.map((item) => ({ ...item, count: notes.filter((note) => note.kind === item.id).length }));
  const visible = filter === "all" ? notes : notes.filter((note) => note.kind === filter);

  return (
    <div className="user-notes">
      {notes.length >= 3 ? (
        <div className="note-filters" role="radiogroup" aria-label={t("notes.filterAria")}>
          <button type="button" role="radio" aria-checked={filter === "all"} className={filter === "all" ? "is-on" : ""} onClick={() => setFilter("all")}>
            {t("notes.filterAll")}
            <span>{notes.length}</span>
          </button>
          {counts
            .filter((item) => item.count > 0)
            .map((item) => (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={filter === item.id}
                className={`kind-${item.id}${filter === item.id ? " is-on" : ""}`}
                onClick={() => setFilter(item.id)}
              >
                <Icon name={item.icon} size={12} />
                {t(`mini.marker_${item.id}`)}
                <span>{item.count}</span>
              </button>
            ))}
        </div>
      ) : null}

      {notes.length === 0 ? (
        <p className="user-notes-empty">{recording ? t("notes.emptyLive") : t("notes.hint")}</p>
      ) : (
        <ol className="user-notes-list" ref={list}>
          {visible.map((note) => (
            <li key={note.id} className={note.kind ? `kind-${note.kind}` : ""}>
              <button
                type="button"
                className={onSeek ? "user-note-time is-seekable" : "user-note-time"}
                onClick={() => onSeek?.(note.at_ms)}
                tabIndex={onSeek ? 0 : -1}
              >
                {formatClock(note.at_ms)}
              </button>
              <div className="user-note-body">
                <KindPicker value={note.kind ?? null} onChange={(next) => void retag(note, next)} />
                {editing === note.id ? (
                  <textarea
                    className="user-note-edit"
                    value={editDraft}
                    autoFocus
                    rows={Math.min(6, Math.max(2, editDraft.split("\n").length))}
                    onChange={(event) => setEditDraft(event.target.value)}
                    onBlur={() => void save(note)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void save(note);
                      }
                      if (event.key === "Escape") setEditing(null);
                    }}
                  />
                ) : (
                  <p
                    className="user-note-text"
                    title={t("notes.editHint")}
                    onDoubleClick={() => {
                      setEditing(note.id);
                      setEditDraft(note.text);
                    }}
                  >
                    {note.text}
                  </p>
                )}
                {note.ai_context && editing !== note.id ? (
                  <p className="user-note-ai">
                    <Icon name="spark" size={12} />
                    <span>{note.ai_context}</span>
                  </p>
                ) : null}
                {suggestion?.noteId === note.id ? (
                  <div className="note-suggestion">
                    {suggestion.text === null && !suggestion.error ? (
                      <AiThinking compact lines={2} steps={[t("notes.expandStep1"), t("notes.expandStep2"), t("notes.expandStep3")]} />
                    ) : suggestion.error ? (
                      <p className="note-suggestion-error">{suggestion.error}</p>
                    ) : (
                      <>
                        <p className="note-suggestion-text">{suggestion.text}</p>
                        <div className="note-suggestion-actions">
                          <button type="button" className="button button-primary button-sm" onClick={() => void applySuggestion(note, "replace")}>
                            {t("notes.replace")}
                          </button>
                          <button type="button" className="button button-ghost button-sm" onClick={() => void applySuggestion(note, "append")}>
                            {t("notes.append")}
                          </button>
                          <button type="button" className="button button-quiet button-sm" onClick={() => setSuggestion(null)}>
                            {t("notes.discard")}
                          </button>
                        </div>
                      </>
                    )}
                    {suggestion.error ? (
                      <button type="button" className="button button-quiet button-sm" onClick={() => setSuggestion(null)}>
                        {t("notes.discard")}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="user-note-actions">
                <button
                  type="button"
                  title={t("notes.expand")}
                  aria-label={t("notes.expand")}
                  disabled={suggestion?.noteId === note.id && suggestion.text === null && !suggestion.error}
                  onClick={() => void expand(note)}
                >
                  <Icon name="spark" size={14} />
                </button>
                <button
                  type="button"
                  title={tasked.has(note.id) ? t("notes.taskCreated") : t("notes.toTask")}
                  aria-label={t("notes.toTask")}
                  disabled={tasked.has(note.id)}
                  onClick={() => void toTask(note)}
                >
                  <Icon name={tasked.has(note.id) ? "check" : "tasks"} size={14} />
                </button>
                {onAsk ? (
                  <button type="button" title={t("notes.ask")} aria-label={t("notes.ask")} onClick={() => onAsk(note.text)}>
                    <Icon name="chat" size={14} />
                  </button>
                ) : null}
                <button type="button" className="is-danger" title={t("common.delete")} aria-label={t("common.delete")} onClick={() => void remove(note)}>
                  <Icon name="trash" size={14} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}

      <div className="user-notes-composer">
        <div className="note-kinds" role="radiogroup" aria-label={t("notes.kindAria")}>
          <InfoTip text={t("notes.shiftHint")} side="top" />
          <button type="button" role="radio" aria-checked={kind === null} className={kind === null ? "is-on" : ""} onClick={() => setKind(null)}>
            {t("notes.free")}
          </button>
          {KINDS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="radio"
              aria-checked={kind === item.id}
              className={`kind-${item.id}${kind === item.id ? " is-on" : ""}`}
              onClick={() => setKind(kind === item.id ? null : item.id)}
            >
              <Icon name={item.icon} size={12} />
              {t(`mini.marker_${item.id}`)}
            </button>
          ))}
        </div>
        <div className="user-notes-input">
          <textarea
            ref={input}
            value={draft}
            rows={Math.min(5, Math.max(2, draft.split("\n").length))}
            placeholder={recording ? t("notes.placeholderLive") : t("notes.placeholder")}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void add();
              }
            }}
          />
          <button type="button" className="button button-primary button-sm" disabled={busy || !draft.trim()} onClick={() => void add()}>
            <Icon name="plus" size={14} />
            {t("notes.add")}
          </button>
        </div>
      </div>
    </div>
  );
}

function KindPicker({ value, onChange }: { value: NoteKind | null; onChange: (next: NoteKind | null) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const current = KINDS.find((item) => item.id === value);
  return (
    <span className="kind-picker" onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className={current ? `kind-badge kind-${current.id}` : "kind-badge is-empty"}
        aria-haspopup="menu"
        aria-expanded={open}
        title={t("notes.changeKind")}
        onClick={() => setOpen((state) => !state)}
      >
        {current ? <Icon name={current.icon} size={11} /> : null}
        {current ? t(`mini.marker_${current.id}`) : t("notes.free")}
      </button>
      {open ? (
        <span className="kind-menu" role="menu">
          {[null, ...KINDS.map((item) => item.id)].map((id) => (
            <button
              key={id ?? "free"}
              type="button"
              role="menuitem"
              className={id ? `kind-${id}` : ""}
              onClick={() => {
                setOpen(false);
                onChange(id);
              }}
            >
              {id ? t(`mini.marker_${id}`) : t("notes.free")}
            </button>
          ))}
        </span>
      ) : null}
    </span>
  );
}
