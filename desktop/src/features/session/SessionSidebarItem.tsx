import { useState, type DragEvent, type KeyboardEvent } from "react";

import type { Session, Tag } from "../../shared/api/types";
import { formatDate } from "../../shared/lib/format";

interface SessionSidebarItemProps {
  session: Session;
  active: boolean;
  folders: Tag[];
  onOpen: () => void;
  onMove: (sessionId: string, folderId: string | null) => Promise<void>;
}

export function SessionSidebarItem({
  session,
  active,
  folders,
  onOpen,
  onMove,
}: SessionSidebarItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moving, setMoving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const assignedIds = new Set((session.tags ?? []).map((folder) => folder.id));

  const move = async (folderId: string | null) => {
    setMoving(true);
    setError(null);
    try {
      await onMove(session.id, folderId);
      setMenuOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível mover a conversa.");
    } finally {
      setMoving(false);
    }
  };

  const handleDragStart = (event: DragEvent<HTMLDivElement>) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-droidnote-session", session.id);
    event.dataTransfer.setData("text/plain", session.id);
    setDragging(true);
  };

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "Escape") return;
    setMenuOpen(false);
    event.currentTarget.focus();
  };

  return (
    <div
      className={[
        "session-entry",
        active ? "is-active" : "",
        dragging ? "is-dragging" : "",
      ].filter(Boolean).join(" ")}
      draggable
      onDragStart={handleDragStart}
      onDragEnd={() => setDragging(false)}
    >
      <div className="session-entry-line">
        <button
          type="button"
          className={active ? "session-item active" : "session-item"}
          onClick={onOpen}
        >
          <span className="session-item-dot" aria-hidden />
          <span className="session-item-copy">
            <strong>{session.title}</strong>
            <span>{formatDate(session.started_at)}</span>
          </span>
        </button>
        <button
          type="button"
          className="sidebar-more"
          aria-label={`Opções de ${session.title}`}
          aria-expanded={menuOpen}
          title="Mais opções"
          onClick={() => setMenuOpen((current) => !current)}
          onKeyDown={handleMenuKeyDown}
        >
          <MoreIcon />
        </button>
      </div>

      {menuOpen ? (
        <div className="session-move-menu">
          <span>Mover para</span>
          <button
            type="button"
            className={!session.tags?.length ? "is-current" : ""}
            disabled={moving}
            onClick={() => void move(null)}
          >
            Sem pasta
          </button>
          {folders.map((folder) => (
            <button
              type="button"
              className={assignedIds.has(folder.id) ? "is-current" : ""}
              disabled={moving}
              key={folder.id}
              onClick={() => void move(folder.id)}
            >
              {folder.name}
            </button>
          ))}
          {error ? <small className="session-move-error" role="alert">{error}</small> : null}
        </div>
      ) : null}
    </div>
  );
}

function MoreIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      <circle cx="4.5" cy="10" r="1" />
      <circle cx="10" cy="10" r="1" />
      <circle cx="15.5" cy="10" r="1" />
    </svg>
  );
}
