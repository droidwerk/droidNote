import {
  forwardRef,
  useEffect,
  useId,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

import type { Session, SessionBulkAction, Tag } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import "./session.css";

export interface SessionRowMenuHandle {
  /** Abre no ponteiro (clique direito) ou, sem ponto, ao lado do "...". */
  openAt: (x?: number, y?: number) => void;
}

interface SessionRowMenuProps {
  session: Session;
  live?: boolean;
  busy?: boolean;
  /** Sem pastas ou sem onMove, o grupo "Mover para" fica de fora. */
  folders?: Tag[];
  onMove?: (folderId: string | null) => void | Promise<void>;
  onRename?: () => void;
  onAction: (action: SessionBulkAction) => void;
  triggerClassName?: string;
}

/** Menu "..." de uma conversa: o mesmo na barra lateral, em Conversas e na página da conversa. */
export const SessionRowMenu = forwardRef<SessionRowMenuHandle, SessionRowMenuProps>(function SessionRowMenu(
  { session, live = false, busy = false, folders, onMove, onRename, onAction, triggerClassName = "sidebar-more" },
  ref,
) {
  const t = useT();
  const [point, setPoint] = useState<{ x: number; y: number; alignRight?: boolean } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const open = point !== null;
  const noteId = useId();

  const openAt = (x?: number, y?: number) => {
    if (x !== undefined && y !== undefined) {
      setPoint({ x, y });
      return;
    }
    const rect = triggerRef.current?.getBoundingClientRect();
    setPoint({ x: rect?.right ?? 0, y: (rect?.bottom ?? 0) + 4, alignRight: true });
  };
  useImperativeHandle(ref, () => ({ openAt }));

  const close = (refocus = true) => {
    setPoint(null);
    if (refocus) triggerRef.current?.focus();
  };

  // Mantém o menu dentro da janela e foca o primeiro item.
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu || !point) return;
    const { width, height } = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(point.x - (point.alignRight ? width : 0), window.innerWidth - width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(point.y, window.innerHeight - height - 8))}px`;
    menu.querySelector<HTMLButtonElement>("[role^='menuitem']")?.focus();
  }, [point]);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) close(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>("[role^='menuitem']") ?? [])];
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const go = (next: number) => items[(next + items.length) % items.length]?.focus();
    if (event.key === "ArrowDown") go(index + 1);
    else if (event.key === "ArrowUp") go(index - 1);
    else if (event.key === "Home") go(0);
    else if (event.key === "End") go(items.length - 1);
    else if (event.key === "Escape") close();
    else if (event.key === "Tab") close(false);
    else return;
    if (event.key !== "Tab") event.preventDefault();
    event.stopPropagation();
  };

  const run = (action: SessionBulkAction) => {
    close();
    onAction(action);
  };

  const locked = live && !session.deleted_at;
  const lockProps = locked ? { "aria-disabled": true as const, "aria-describedby": noteId, title: t("archive.liveLocked") } : {};
  const assigned = new Set((session.tags ?? []).map((tag) => tag.id));

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={triggerClassName}
        aria-label={t("folders.sessionOptions", { title: session.title })}
        aria-haspopup="menu"
        aria-expanded={open}
        title={t("folders.more")}
        disabled={busy}
        onClick={(event) => {
          event.stopPropagation();
          if (open) close(false);
          else openAt();
        }}
      >
        <MoreIcon />
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              className="session-row-menu popover"
              role="menu"
              aria-label={session.title}
              onKeyDown={onMenuKey}
              onClick={(event) => event.stopPropagation()}
            >
              {session.deleted_at ? (
                <>
                  <button type="button" role="menuitem" onClick={() => run("restore")}>
                    {t("archive.restore")}
                  </button>
                  <hr />
                  <button type="button" role="menuitem" className="is-danger" onClick={() => run("purge")}>
                    {t("archive.purge")}
                  </button>
                </>
              ) : (
                <>
                  {folders && onMove ? (
                    <div role="group" aria-label={t("folders.moveTo")} className="session-row-menu-group">
                      <span aria-hidden>{t("folders.moveTo")}</span>
                      {[{ id: null, name: t("folders.noFolder") }, ...folders].map((folder) => {
                        const current = folder.id ? assigned.has(folder.id) : assigned.size === 0;
                        return (
                          <button
                            key={folder.id ?? "none"}
                            type="button"
                            role="menuitemradio"
                            aria-checked={current}
                            className={current ? "is-current" : ""}
                            onClick={() => {
                              close();
                              void onMove(folder.id);
                            }}
                          >
                            {folder.name}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  {onRename ? (
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        close(false);
                        onRename();
                      }}
                    >
                      {t("archive.rename")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    role="menuitem"
                    {...lockProps}
                    onClick={() => !locked && run(session.archived_at ? "unarchive" : "archive")}
                  >
                    {session.archived_at ? t("archive.unarchive") : t("archive.archive")}
                    <kbd>E</kbd>
                  </button>
                  <hr />
                  <button type="button" role="menuitem" className="is-danger" {...lockProps} onClick={() => !locked && run("trash")}>
                    {t("common.delete")}
                    <kbd>Del</kbd>
                  </button>
                  {locked ? <small id={noteId} className="session-row-menu-note">{t("archive.liveLocked")}</small> : null}
                </>
              )}
            </div>,
            document.body,
          )
        : null}
    </>
  );
});

/** Teclas de uma linha com foco: E arquiva, Delete/Backspace apaga, Shift+F10 ou a tecla de menu abre o menu. */
export function rowKeyAction(event: KeyboardEvent, session: Session): SessionBulkAction | "menu" | null {
  if ((event.target as HTMLElement).closest("input, textarea, select, [role='menu']")) return null;
  if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) return "menu";
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (session.deleted_at) return null;
  if (event.key.toLowerCase() === "e" && !event.shiftKey) return session.archived_at ? "unarchive" : "archive";
  if (event.key === "Delete" || event.key === "Backspace") return "trash";
  return null;
}

export function MoreIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      <circle cx="4.5" cy="10" r="1" />
      <circle cx="10" cy="10" r="1" />
      <circle cx="15.5" cy="10" r="1" />
    </svg>
  );
}
