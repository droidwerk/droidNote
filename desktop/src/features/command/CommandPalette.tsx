import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../../shared/api/client";
import type { SearchResult, Session } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatClock, formatDate, highlight } from "../../shared/lib/format";
import { Icon, type IconName } from "../../shared/ui/Icon";

interface CommandPaletteProps {
  open: boolean;
  sessions: Session[];
  recording: boolean;
  onClose: () => void;
  onOpenSession: (sessionId: string, atMs?: number) => void;
  onToggleCapture: () => void;
  onOpenChat: () => void;
  onOpenSettings: () => void;
  onOpenLive: () => void;
  onOpenTasks: () => void;
}

const NO_HITS: SearchResult = { query: "", segments: [], notes: [], summaries: [], tasks: [] };

interface Item {
  key: string;
  group: "actions" | "sessions" | "notes" | "minutes" | "tasks" | "excerpts";
  icon: IconName;
  title: string;
  meta?: string;
  excerpt?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  sessions,
  recording,
  onClose,
  onOpenSession,
  onToggleCapture,
  onOpenChat,
  onOpenSettings,
  onOpenLive,
  onOpenTasks,
}: CommandPaletteProps) {
  const t = useT();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchResult>(NO_HITS);
  const [searching, setSearching] = useState(false);
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setHits(NO_HITS);
    setCursor(0);
    window.setTimeout(() => input.current?.focus(), 10);
  }, [open]);

  useEffect(() => {
    const cleaned = query.trim();
    if (!open || cleaned.length < 2) {
      setHits(NO_HITS);
      setSearching(false);
      return undefined;
    }
    setSearching(true);
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api
        .search(cleaned)
        .then((result) => {
          if (!cancelled) setHits({ ...NO_HITS, ...result, segments: result.segments.slice(0, 12) });
        })
        .catch(() => {
          if (!cancelled) setHits(NO_HITS);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, open]);

  const titles = useMemo(() => new Map(sessions.map((item) => [item.id, item])), [sessions]);

  const items = useMemo<Item[]>(() => {
    const cleaned = query.trim().toLowerCase();
    const actions: Item[] = [
      {
        key: "capture",
        group: "actions",
        icon: recording ? "pause" : "console",
        title: recording ? t("palette.stopCapture") : t("palette.startCapture"),
        meta: "Ctrl+Shift+R",
        run: onToggleCapture,
      },
      { key: "live", group: "actions", icon: "console", title: t("palette.openLive"), run: onOpenLive },
      { key: "chat", group: "actions", icon: "chat", title: t("palette.newChat"), run: onOpenChat },
      { key: "settings", group: "actions", icon: "settings", title: t("palette.openSettings"), run: onOpenSettings },
    ].filter((item) => !cleaned || item.title.toLowerCase().includes(cleaned)) as Item[];
    const sessionItems: Item[] = sessions
      .filter((item) => !cleaned || item.title.toLowerCase().includes(cleaned))
      .slice(0, cleaned ? 6 : 5)
      .map((item) => ({
        key: `s-${item.id}`,
        group: "sessions",
        icon: modeIcon(item.capture_mode),
        title: item.title,
        meta: formatDate(item.started_at),
        run: () => onOpenSession(item.id),
      }));
    const sessionTitle = (id: string | null) => (id ? titles.get(id)?.title : undefined) ?? "—";
    const noteItems: Item[] = hits.notes.map((note) => ({
      key: `n-${note.id}`,
      group: "notes",
      icon: "dictation",
      title: sessionTitle(note.session_id),
      meta: formatClock(note.at_ms),
      excerpt: note.text,
      run: () => onOpenSession(note.session_id, note.at_ms),
    }));
    const minuteItems: Item[] = hits.summaries.map((hit) => ({
      key: `m-${hit.session_id}`,
      group: "minutes",
      icon: "spark",
      title: sessionTitle(hit.session_id),
      excerpt: hit.excerpt,
      run: () => onOpenSession(hit.session_id),
    }));
    const taskItems: Item[] = hits.tasks.map((task) => ({
      key: `t-${task.id}`,
      group: "tasks",
      icon: "tasks",
      title: task.text,
      meta: task.done ? t("palette.taskDone") : task.session_id ? sessionTitle(task.session_id) : undefined,
      run: onOpenTasks,
    }));
    const excerptItems: Item[] = hits.segments.map((segment) => ({
      key: `e-${segment.id}`,
      group: "excerpts",
      icon: "voice",
      title: sessionTitle(segment.session_id),
      meta: formatClock(segment.start_ms),
      excerpt: segment.text,
      run: () => onOpenSession(segment.session_id, segment.start_ms),
    }));
    return [...actions, ...sessionItems, ...noteItems, ...minuteItems, ...taskItems, ...excerptItems];
  }, [query, hits, sessions, recording, titles, t, onToggleCapture, onOpenLive, onOpenChat, onOpenSettings, onOpenSession, onOpenTasks]);

  useEffect(() => {
    if (cursor >= items.length) setCursor(Math.max(0, items.length - 1));
  }, [items.length, cursor]);

  useEffect(() => {
    const node = list.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`);
    node?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!open) return null;

  const run = (item: Item | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  const groups: { id: Item["group"]; label: string }[] = [
    { id: "actions", label: t("palette.actions") },
    { id: "sessions", label: t("palette.sessions") },
    { id: "notes", label: t("palette.notes") },
    { id: "minutes", label: t("palette.minutes") },
    { id: "tasks", label: t("palette.tasks") },
    { id: "excerpts", label: t("palette.excerpts") },
  ];

  return createPortal(
    <div
      className="palette-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="palette panel" role="dialog" aria-modal="true" aria-label={t("palette.open")}>
        <div className="palette-input">
          <Icon name="search" />
          <input
            ref={input}
            value={query}
            placeholder={t("palette.placeholder")}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              } else if (event.key === "ArrowDown") {
                event.preventDefault();
                setCursor((value) => Math.min(items.length - 1, value + 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setCursor((value) => Math.max(0, value - 1));
              } else if (event.key === "Enter") {
                event.preventDefault();
                run(items[cursor]);
              }
            }}
          />
          <kbd>Esc</kbd>
        </div>
        <div className="palette-list" ref={list}>
          {items.length === 0 ? (
            <p className="palette-empty">{searching ? t("palette.searching") : t("palette.empty")}</p>
          ) : (
            groups.map((group) => {
              const rows = items.filter((item) => item.group === group.id);
              if (rows.length === 0) return null;
              return (
                <div key={group.id} className="palette-group">
                  <span className="eyebrow">{group.label}</span>
                  {rows.map((item) => {
                    const index = items.indexOf(item);
                    return (
                      <button
                        key={item.key}
                        type="button"
                        data-index={index}
                        className={index === cursor ? "palette-item is-active" : "palette-item"}
                        onMouseEnter={() => setCursor(index)}
                        onClick={() => run(item)}
                      >
                        <Icon name={item.icon} size={16} />
                        <span className="palette-copy">
                          <strong>{item.title}</strong>
                          {item.excerpt ? (
                            <span className="palette-excerpt">
                              {highlight(item.excerpt, query).map((part, partIndex) =>
                                part.toLowerCase() === query.trim().toLowerCase() ? (
                                  <mark key={partIndex}>{part}</mark>
                                ) : (
                                  <span key={partIndex}>{part}</span>
                                ),
                              )}
                            </span>
                          ) : null}
                        </span>
                        {item.meta ? <small>{item.meta}</small> : null}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
          {searching && items.length > 0 ? <p className="palette-empty">{t("palette.searching")}</p> : null}
        </div>
        <div className="palette-foot">{t("palette.hint")}</div>
      </div>
    </div>,
    document.body,
  );
}

export function modeIcon(mode: Session["capture_mode"]): IconName {
  if (mode === "dictation") return "dictation";
  if (mode === "lecture") return "lecture";
  return "meeting";
}
