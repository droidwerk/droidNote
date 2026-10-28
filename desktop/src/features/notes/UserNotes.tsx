import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../shared/api/client";
import type { UserNote } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatClock } from "../../shared/lib/format";
import { Icon } from "../../shared/ui/Icon";

interface UserNotesProps {
  sessionId: string;
  recording: boolean;
  /** Momento atual (reprodução da sessão); sem ele, o servidor usa o instante da gravação. */
  momentMs?: number | null;
  revision?: number;
  onSeek?: (ms: number) => void;
}

/** Suas anotações: cada linha fica presa ao momento da fala e entra na nota final. */
export function UserNotes({ sessionId, recording, momentMs = null, revision = 0, onSeek }: UserNotesProps) {
  const t = useT();
  const [notes, setNotes] = useState<UserNote[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
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
      const note = await api.addNote(sessionId, text, recording ? null : momentMs);
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
    setNotes(await api.updateNote(sessionId, note.id, text));
  };

  const remove = async (note: UserNote) => {
    await api.deleteNote(sessionId, note.id);
    setNotes((current) => current.filter((item) => item.id !== note.id));
  };

  return (
    <div className="user-notes">
      <p className="user-notes-hint">{t("notes.hint")}</p>
      {notes.length === 0 ? (
        <p className="user-notes-empty">{recording ? t("notes.emptyLive") : t("notes.empty")}</p>
      ) : (
        <ol className="user-notes-list" ref={list}>
          {notes.map((note) => (
            <li key={note.id}>
              <button
                type="button"
                className={onSeek ? "user-note-time is-seekable" : "user-note-time"}
                onClick={() => onSeek?.(note.at_ms)}
                tabIndex={onSeek ? 0 : -1}
              >
                {formatClock(note.at_ms)}
              </button>
              {editing === note.id ? (
                <textarea
                  className="user-note-edit"
                  value={editDraft}
                  autoFocus
                  rows={2}
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
                  onDoubleClick={() => {
                    setEditing(note.id);
                    setEditDraft(note.text);
                  }}
                >
                  {note.text}
                </p>
              )}
              <button type="button" className="user-note-remove" aria-label={t("common.delete")} onClick={() => void remove(note)}>
                <Icon name="close" size={13} />
              </button>
            </li>
          ))}
        </ol>
      )}
      <div className="user-notes-composer">
        <textarea
          ref={input}
          value={draft}
          rows={2}
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
  );
}
