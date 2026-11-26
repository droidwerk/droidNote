import { useRef, useState, type DragEvent } from "react";

import type { Session, SessionBulkAction, Tag } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatClock, withoutTrailingDate } from "../../shared/lib/format";
import { Icon } from "../../shared/ui/Icon";
import { useToast } from "../../shared/ui/Toast";
import { modeIcon } from "../command/CommandPalette";
import { rowKeyAction, SessionRowMenu, type SessionRowMenuHandle } from "./SessionRowMenu";

interface SessionSidebarItemProps {
  session: Session;
  active: boolean;
  live?: boolean;
  busy?: boolean;
  folders: Tag[];
  onOpen: () => void;
  onMove: (sessionId: string, folderId: string | null) => Promise<void>;
  onRename: (sessionId: string, title: string) => Promise<void>;
  onAction: (session: Session, action: SessionBulkAction) => void;
}

export function SessionSidebarItem({
  session,
  active,
  live = false,
  busy = false,
  folders,
  onOpen,
  onMove,
  onRename,
  onAction,
}: SessionSidebarItemProps) {
  const t = useT();
  const toast = useToast();
  const menu = useRef<SessionRowMenuHandle>(null);
  const [dragging, setDragging] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);

  const move = async (folderId: string | null) => {
    try {
      await onMove(session.id, folderId);
    } catch (cause) {
      toast.push({ tone: "error", title: cause instanceof Error ? cause.message : t("folders.moveFail") });
    }
  };

  const commitRename = async () => {
    const title = draft?.trim();
    setDraft(null);
    if (!title || title === session.title) return;
    try {
      await onRename(session.id, title);
    } catch (cause) {
      toast.push({ tone: "error", title: cause instanceof Error ? cause.message : String(cause) });
    }
  };

  const handleDragStart = (event: DragEvent<HTMLDivElement>) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-droidnote-session", session.id);
    event.dataTransfer.setData("text/plain", session.id);
    setDragging(true);
  };

  return (
    <div
      className={[
        "session-entry",
        active ? "is-active" : "",
        dragging ? "is-dragging" : "",
        busy ? "is-busy" : "",
      ].filter(Boolean).join(" ")}
      draggable={draft === null}
      onDragStart={handleDragStart}
      onDragEnd={() => setDragging(false)}
      onContextMenu={(event) => {
        event.preventDefault();
        menu.current?.openAt(event.clientX, event.clientY);
      }}
      onKeyDown={(event) => {
        const action = rowKeyAction(event, session);
        if (!action) return;
        event.preventDefault();
        if (action === "menu") menu.current?.openAt();
        else if (live) toast.push({ tone: "info", title: t("archive.liveLocked") });
        else onAction(session, action);
      }}
    >
      <div className="session-entry-line">
        {draft !== null ? (
          <input
            className="input session-entry-rename"
            value={draft}
            autoFocus
            maxLength={200}
            aria-label={t("archive.rename")}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => void commitRename()}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
              if (event.key === "Escape") setDraft(null);
            }}
          />
        ) : (
          <button
            type="button"
            data-session-row={session.id}
            className={active ? "session-item active" : "session-item"}
            onClick={onOpen}
          >
            <span className={live ? "session-item-mode is-live" : "session-item-mode"} aria-hidden>
              <Icon name={modeIcon(session.capture_mode)} size={14} />
            </span>
            <span className="session-item-copy">
              <strong title={session.title}>{withoutTrailingDate(session.title)}</strong>
              <span>
                {new Date(session.started_at).toLocaleTimeString(document.documentElement.lang || undefined, { hour: "2-digit", minute: "2-digit" })}
                {" · "}
                {formatClock(session.duration_ms)}
              </span>
            </span>
          </button>
        )}
        <SessionRowMenu
          ref={menu}
          session={session}
          live={live}
          busy={busy}
          folders={folders}
          onMove={move}
          onRename={() => setDraft(session.title)}
          onAction={(action) => onAction(session, action)}
        />
      </div>
    </div>
  );
}
