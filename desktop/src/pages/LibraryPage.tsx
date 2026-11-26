import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent } from "react";

import { api } from "../shared/api/client";
import type { Session, SessionBulkAction, Tag } from "../shared/api/types";
import { pluralForm, useI18n } from "../shared/i18n";
import { bcp47 } from "../shared/i18n/locales";
import { formatClock, withoutTrailingDate } from "../shared/lib/format";
import { useFlag } from "../shared/lib/useFlag";
import { InfoTip } from "../shared/ui/InfoTip";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { Icon } from "../shared/ui/Icon";
import { Button } from "../shared/ui/primitives";
import { useToast } from "../shared/ui/Toast";
import { modeIcon } from "../features/command/CommandPalette";
import { TourButton } from "../features/onboarding/Tour";
import { rowKeyAction, SessionRowMenu, type SessionRowMenuHandle } from "../features/session/SessionRowMenu";
import { daysSince, useSessionActions } from "../features/session/useSessionActions";

const DRAG_TYPE = "application/x-droidnote-session";

/** "archived" e "trash" são as duas entradas virtuais no fim do trilho de pastas. */
type FolderFilter = "all" | "none" | "archived" | "trash" | string;
type Sort = "recent" | "oldest" | "longest" | "title";

interface LibraryPageProps {
  sessions: Session[];
  folders: Tag[];
  liveSessionId: string | null;
  onOpenSession: (sessionId: string) => void;
  onChanged: () => Promise<void> | void;
  /** Leva para Ao vivo: o estado vazio do primeiro uso oferece gravar. */
  onGoLive?: () => void;
}

/** Conversas: pastas à esquerda, lista à direita, seleção (Ctrl, Shift, Ctrl+A) para mover, arquivar ou apagar várias de uma vez. */
export function LibraryPage({ sessions, folders, liveSessionId, onOpenSession, onChanged, onGoLive }: LibraryPageProps) {
  const { t, locale } = useI18n();
  const confirm = useConfirm();
  const toast = useToast();
  const [filter, setFilter] = useState<FolderFilter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("recent");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [renaming, setRenaming] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [dropTarget, setDropTarget] = useState<FolderFilter | null>(null);
  const [busy, setBusy] = useState(false);
  const [foldersCollapsed, toggleFolders] = useFlag("droidnote.libraryFoldersCollapsed");
  const [archived, setArchived] = useState<Session[]>([]);
  const [trash, setTrash] = useState<Session[]>([]);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const [titleDraft, setTitleDraft] = useState<{ id: string; value: string } | null>(null);
  const anchor = useRef<string | null>(null);
  const menus = useRef(new Map<string, SessionRowMenuHandle>());

  // As listas de arquivadas e lixeira vêm do mesmo GET /sessions, com scope.
  const loadExtra = useCallback(async () => {
    const [nextArchived, nextTrash] = await Promise.all([
      api.sessions(undefined, "archived").catch(() => [] as Session[]),
      api.sessions(undefined, "trash").catch(() => [] as Session[]),
    ]);
    setArchived(nextArchived);
    setTrash(nextTrash);
  }, []);
  useEffect(() => {
    void loadExtra();
  }, [loadExtra]);

  const refresh = useCallback(async () => {
    await Promise.all([onChanged(), loadExtra()]);
  }, [onChanged, loadExtra]);
  const actions = useSessionActions(refresh, liveSessionId);
  const virtual = filter === "archived" || filter === "trash";
  const source = filter === "archived" ? archived : filter === "trash" ? trash : sessions;

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    let loose = 0;
    for (const session of sessions) {
      const tags = session.tags ?? [];
      if (!tags.length) loose += 1;
      for (const tag of tags) map.set(tag.id, (map.get(tag.id) ?? 0) + 1);
    }
    return { map, loose };
  }, [sessions]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = source.filter((session) => {
      const tags = session.tags ?? [];
      if (filter === "none" && tags.length) return false;
      if (!virtual && filter !== "all" && filter !== "none" && !tags.some((tag) => tag.id === filter)) return false;
      return !needle || session.title.toLowerCase().includes(needle);
    });
    const by: Record<Sort, (a: Session, b: Session) => number> = {
      recent: (a, b) => b.started_at.localeCompare(a.started_at),
      oldest: (a, b) => a.started_at.localeCompare(b.started_at),
      longest: (a, b) => b.duration_ms - a.duration_ms,
      title: (a, b) => a.title.localeCompare(b.title, bcp47(locale)),
    };
    return [...list].sort(by[sort]);
  }, [source, virtual, filter, query, sort, locale]);

  const allChecked = visible.length > 0 && visible.every((session) => selected.has(session.id));
  const toggleAll = () =>
    setSelected(allChecked ? new Set() : new Set(visible.map((session) => session.id)));
  const toggle = (id: string) => {
    anchor.current = id;
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  /** Shift: da última linha clicada até esta, na ordem que está na tela. */
  const selectRange = (id: string) => {
    const from = visible.findIndex((session) => session.id === anchor.current);
    const to = visible.findIndex((session) => session.id === id);
    if (from < 0 || to < 0) return toggle(id);
    const [start, end] = from < to ? [from, to] : [to, from];
    setSelected(new Set(visible.slice(start, end + 1).map((session) => session.id)));
  };
  const pick = (event: MouseEvent, id: string) => {
    if (event.shiftKey) selectRange(id);
    else toggle(id);
  };

  // Ao trocar de pasta, a seleção e a âncora começam de novo.
  useEffect(() => {
    setSelected(new Set());
    anchor.current = null;
  }, [filter]);

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
      await refresh();
    } catch (err) {
      toast.push({ tone: "error", title: err instanceof Error ? err.message : t("folders.moveFail") });
    } finally {
      setBusy(false);
    }
  };

  const moveMany = (ids: string[], folderId: string | null) =>
    run(async () => {
      await Promise.all(ids.map((id) => api.setSessionTags(id, folderId ? [folderId] : [])));
      setSelected(new Set());
      const folder = folders.find((item) => item.id === folderId);
      toast.push({
        tone: "success",
        title: folder ? t("library.movedTo", { count: ids.length, name: folder.name }) : t("library.movedOut", { count: ids.length }),
      });
    });

  /** Arquivar, desarquivar, lixeira, restaurar ou apagar de vez: as que falharem continuam selecionadas. */
  const act = async (ids: string[], action: SessionBulkAction, all = false) => {
    const targets = source.filter((session) => ids.includes(session.id));
    if (!targets.length) return;
    const firstIndex = visible.findIndex((session) => ids.includes(session.id));
    setBusy(true);
    setPendingIds(new Set(ids));
    const result = action === "purge" ? await actions.purge(targets, all) : await actions.apply(targets, action);
    setPendingIds(new Set());
    setBusy(false);
    if (!result) return;
    setSelected(new Set(result.failed.map((item) => item.id)));
    // O foco vai para a linha que ficou no lugar, nunca para o body.
    requestAnimationFrame(() => {
      const rows = [...document.querySelectorAll<HTMLElement>(".library-table [data-session-row]")];
      (rows[Math.min(firstIndex, rows.length - 1)] ?? document.querySelector<HTMLElement>(".library-folder.is-on"))?.focus();
    });
  };

  const renameSession = async () => {
    const draft = titleDraft;
    setTitleDraft(null);
    const session = source.find((item) => item.id === draft?.id);
    const title = draft?.value.trim();
    if (!session || !title || title === session.title) return;
    await run(() => api.renameSession(session.id, title).then(loadExtra));
  };

  const onListKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest("input, select, textarea, [role='menu']")) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      event.preventDefault();
      setSelected(new Set(visible.map((session) => session.id)));
      return;
    }
    if (event.key === "Escape" && selected.size) {
      event.preventDefault();
      setSelected(new Set());
      return;
    }
    const rowId = target.closest<HTMLElement>("[data-row-id]")?.dataset.rowId;
    const focused = visible.find((session) => session.id === rowId);
    if (!focused) return;
    const ids = selected.size ? [...selected] : [focused.id];
    if (filter === "trash" && event.key === "Delete") {
      event.preventDefault();
      void act(ids, "purge");
      return;
    }
    const action = rowKeyAction(event, focused);
    if (!action) return;
    event.preventDefault();
    if (action === "menu") menus.current.get(focused.id)?.openAt();
    else void act(ids, action);
  };

  const createFolder = (name: string) =>
    run(async () => {
      const folder = await api.createTag(name);
      setNewName("");
      setCreating(false);
      setFilter(folder.id);
    });

  const rename = (folder: Tag) => {
    const name = nameDraft.trim();
    setRenaming(null);
    if (!name || name === folder.name) return;
    void run(() => api.renameTag(folder.id, name));
  };

  const removeFolder = async (folder: Tag) => {
    const count = counts.map.get(folder.id) ?? 0;
    const ok = await confirm({
      title: t("folders.deleteTitle", { name: folder.name }),
      description: count ? (count === 1 ? t("folders.deleteOne") : t("folders.deleteMany", { count })) : undefined,
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    if (filter === folder.id) setFilter("all");
    await run(() => api.deleteTag(folder.id));
  };

  const dropProps = (target: FolderFilter) => ({
    onDragOver: (event: DragEvent) => {
      const types = [...event.dataTransfer.types];
      if (!(types.includes(DRAG_TYPE) || types.includes("text/plain")) || target === "all" || target === filter) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      setDropTarget(target);
    },
    onDragLeave: () => setDropTarget(null),
    onDrop: (event: DragEvent) => {
      event.preventDefault();
      setDropTarget(null);
      const id = event.dataTransfer.getData(DRAG_TYPE);
      if (!id) return;
      const ids = selected.has(id) ? [...selected] : [id];
      if (target === "archived") void act(ids, "archive");
      else if (target === "trash") void act(ids, "trash");
      else void moveMany(ids, target === "none" ? null : target);
    },
  });

  const tag = bcp47(locale);
  const when = (iso: string) =>
    new Date(iso).toLocaleDateString(tag, { day: "2-digit", month: "short", year: new Date(iso).getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
  const hour = (iso: string) => new Date(iso).toLocaleTimeString(tag, { hour: "2-digit", minute: "2-digit" });
  const filterName =
    filter === "all"
      ? t("folders.all")
      : filter === "none"
        ? t("folders.noFolder")
        : filter === "archived"
          ? t("archive.archived")
          : filter === "trash"
            ? t("archive.trash")
            : folders.find((item) => item.id === filter)?.name ?? "";
  const deletedAgo = (iso: string) => {
    const days = daysSince(iso);
    return days ? t(`archive.deletedAgo.${pluralForm(locale, days)}`, { count: days }) : t("archive.deletedToday");
  };

  return (
    <div className="page library">
      <header className="page-head">
        <div className="page-head-copy">
          <h1>{t("library.title")}</h1>
        </div>
        <div className="page-actions">
          <TourButton chapter="conversas" />
        </div>
      </header>

      <div className={foldersCollapsed ? "library-body is-folders-collapsed" : "library-body"}>
        <nav data-tour="folders" className="library-folders" aria-label={t("folders.title")}>
          <button
            type="button"
            className="rail-toggle library-rail-toggle"
            onClick={toggleFolders}
            title={foldersCollapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
            aria-label={foldersCollapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
            aria-expanded={!foldersCollapsed}
          >
            <Icon name="rail" size={15} />
          </button>
          <button
            type="button"
            className={filter === "all" ? "library-folder is-on" : "library-folder"}
            onClick={() => setFilter("all")}
          >
            <Icon name="folder" size={15} />
            <span>{t("folders.all")}</span>
            <small>{sessions.length}</small>
          </button>
          <button
            type="button"
            className={[filter === "none" ? "library-folder is-on" : "library-folder", dropTarget === "none" ? "is-drop" : ""].join(" ")}
            onClick={() => setFilter("none")}
            {...dropProps("none")}
          >
            <Icon name="folder" size={15} />
            <span>{t("folders.noFolder")}</span>
            <small>{counts.loose}</small>
          </button>

          <div className="library-folders-head">
            <span className="with-tip">
              {t("folders.title")}
              <InfoTip text={t("library.dragHint")} />
            </span>
            <button type="button" className="library-add" title={t("folders.create")} aria-label={t("folders.create")} onClick={() => setCreating(true)}>
              <Icon name="plus" size={14} />
            </button>
          </div>

          {folders.map((folder) =>
            renaming === folder.id ? (
              <input
                key={folder.id}
                className="library-folder-input"
                value={nameDraft}
                autoFocus
                maxLength={40}
                aria-label={t("library.rename")}
                onChange={(event) => setNameDraft(event.target.value)}
                onBlur={() => rename(folder)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") event.currentTarget.blur();
                  if (event.key === "Escape") setRenaming(null);
                }}
              />
            ) : (
              <div
                key={folder.id}
                className={[
                  "library-folder-row",
                  filter === folder.id ? "is-on" : "",
                  dropTarget === folder.id ? "is-drop" : "",
                ].join(" ")}
                {...dropProps(folder.id)}
              >
                <button
                  type="button"
                  className="library-folder"
                  onClick={() => setFilter(folder.id)}
                  onDoubleClick={() => {
                    setRenaming(folder.id);
                    setNameDraft(folder.name);
                  }}
                  title={t("library.renameHint")}
                >
                  <Icon name="folder" size={15} />
                  <span>{folder.name}</span>
                  <small>{counts.map.get(folder.id) ?? 0}</small>
                </button>
                <span className="library-folder-tools">
                  <button
                    type="button"
                    title={t("library.rename")}
                    aria-label={t("library.rename")}
                    onClick={() => {
                      setRenaming(folder.id);
                      setNameDraft(folder.name);
                    }}
                  >
                    <Icon name="edit" size={13} />
                  </button>
                  <button type="button" title={t("folders.deleteFolder")} aria-label={t("folders.deleteFolder")} onClick={() => void removeFolder(folder)}>
                    <Icon name="trash" size={13} />
                  </button>
                </span>
              </div>
            ),
          )}

          {creating ? (
            <input
              className="library-folder-input"
              value={newName}
              autoFocus
              maxLength={40}
              placeholder={t("folders.name")}
              aria-label={t("folders.newName")}
              onChange={(event) => setNewName(event.target.value)}
              onBlur={() => (newName.trim() ? void createFolder(newName.trim()) : setCreating(false))}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") {
                  setNewName("");
                  setCreating(false);
                }
              }}
            />
          ) : folders.length === 0 ? (
            <p className="library-hint">{t("library.foldersHint")}</p>
          ) : (
            <p className="library-hint">{t("library.dragHint")}</p>
          )}

          <hr className="library-rail-divider" />
          <button
            type="button"
            className={[filter === "archived" ? "library-folder is-on" : "library-folder", dropTarget === "archived" ? "is-drop" : ""].join(" ")}
            onClick={() => setFilter("archived")}
            {...dropProps("archived")}
          >
            <Icon name="archive" size={15} />
            <span>{t("archive.archived")}</span>
            <small>{archived.length}</small>
          </button>
          {trash.length || filter === "trash" ? (
            <div
              className={["library-folder-row", filter === "trash" ? "is-on" : "", dropTarget === "trash" ? "is-drop" : ""].join(" ")}
              {...dropProps("trash")}
            >
              <button type="button" className="library-folder" onClick={() => setFilter("trash")}>
                <Icon name="trash" size={15} />
                <span>{t("archive.trash")}</span>
                <small>{trash.length}</small>
              </button>
              {trash.length ? (
                <span className="library-folder-tools">
                  <button
                    type="button"
                    title={t("archive.emptyTrash")}
                    aria-label={t("archive.emptyTrash")}
                    disabled={busy}
                    onClick={() => void act(trash.map((session) => session.id), "purge", true)}
                  >
                    <Icon name="trash" size={13} />
                  </button>
                </span>
              ) : null}
            </div>
          ) : null}
        </nav>

        <section className="library-main">
          <div data-tour="library-search" className="library-toolbar">
            {selected.size ? (
              <div className="library-bulk" role="group" aria-label={t("library.selected", { count: selected.size })} aria-busy={busy}>
                <strong>{t("library.selected", { count: selected.size })}</strong>
                {filter === "trash" ? (
                  <>
                    <button type="button" className="tool-btn" disabled={busy} onClick={() => void act([...selected], "restore")}>
                      {t("archive.restore")}
                    </button>
                    <button type="button" className="tool-btn is-danger" disabled={busy} onClick={() => void act([...selected], "purge")}>
                      <Icon name="trash" size={14} />
                      <span>{t("archive.purge")}</span>
                    </button>
                  </>
                ) : (
                  <>
                <select
                  className="select"
                  value=""
                  disabled={busy}
                  aria-label={t("folders.moveTo")}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (!value) return;
                    void moveMany([...selected], value === "__none" ? null : value);
                  }}
                >
                  <option value="">{t("folders.moveTo")}…</option>
                  <option value="__none">{t("folders.noFolder")}</option>
                  {folders.map((folder) => (
                    <option key={folder.id} value={folder.id}>
                      {folder.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="tool-btn"
                  disabled={busy}
                  onClick={() => void act([...selected], filter === "archived" ? "unarchive" : "archive")}
                >
                  {filter === "archived" ? t("archive.unarchive") : t("archive.archive")}
                </button>
                <button type="button" className="tool-btn is-danger" disabled={busy} onClick={() => void act([...selected], "trash")}>
                  <Icon name="trash" size={14} />
                  <span>{t("common.delete")}</span>
                </button>
                  </>
                )}
                <button type="button" className="tool-btn" onClick={() => setSelected(new Set())}>
                  {t("library.clear")}
                </button>
              </div>
            ) : (
              <>
                <span className="library-scope">
                  {filterName}
                  <small>{visible.length}</small>
                </span>
                <label className="search-field">
                  <Icon name="search" size={15} />
                  <input
                    aria-label={t("library.search")}
                    placeholder={t("library.search")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <select className="select library-sort" value={sort} aria-label={t("library.sort")} onChange={(event) => setSort(event.target.value as Sort)}>
                  {(["recent", "oldest", "longest", "title"] as const).map((id) => (
                    <option key={id} value={id}>
                      {t(`library.sort_${id}`)}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>

          {filter === "trash" && trash.length ? <p className="library-note">{t("archive.trashNote")}</p> : null}
          {virtual && source.length === 0 ? (
            <div className="library-empty">
              <strong>{filter === "archived" ? t("archive.archivedEmpty") : t("archive.trashEmpty")}</strong>
            </div>
          ) : sessions.length === 0 && !virtual ? (
            <div className="library-empty">
              <strong>{t("library.firstEmpty")}</strong>
              {onGoLive ? (
                <Button variant="primary" onClick={onGoLive}>
                  <Icon name="mic" size={15} />
                  {t("library.firstRecord")}
                </Button>
              ) : null}
            </div>
          ) : visible.length === 0 ? (
            <div className="library-empty">
              <strong>{query ? t("library.noMatch") : t("library.emptyFolder")}</strong>
              {!query && filter !== "all" ? <small>{t("library.emptyFolderHint")}</small> : null}
            </div>
          ) : (
            <div className="library-table" role="table" onKeyDown={onListKey}>
              <div className="library-row library-row-head" role="row">
                <label data-tour="library-select" className="library-check" role="columnheader">
                  <input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label={t("library.selectAll")} />
                </label>
                <span role="columnheader">{t("library.colTitle")}</span>
                <span role="columnheader">{t("folders.title")}</span>
                <span role="columnheader">{t("library.colDate")}</span>
                <span role="columnheader" className="is-num">{t("library.colLength")}</span>
              </div>
              {visible.map((session, index) => {
                const checked = selected.has(session.id);
                const live = session.id === liveSessionId;
                return (
                  <div
                    key={session.id}
                    role="row"
                    data-row-id={session.id}
                    data-tour={index === 0 ? "library-first" : undefined}
                    className={["library-row", checked ? "is-checked" : "", pendingIds.has(session.id) ? "is-busy" : ""].filter(Boolean).join(" ")}
                    draggable={titleDraft?.id !== session.id}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      menus.current.get(session.id)?.openAt(event.clientX, event.clientY);
                    }}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData(DRAG_TYPE, session.id);
                      event.dataTransfer.setData("text/plain", session.title);
                    }}
                  >
                    <label className="library-check">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => undefined}
                        onClick={(event) => pick(event, session.id)}
                        aria-label={session.title}
                      />
                    </label>
                    {titleDraft?.id === session.id ? (
                      <input
                        className="input library-title-input"
                        value={titleDraft.value}
                        autoFocus
                        maxLength={200}
                        aria-label={t("archive.rename")}
                        onChange={(event) => setTitleDraft({ id: session.id, value: event.target.value })}
                        onBlur={() => void renameSession()}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") event.currentTarget.blur();
                          if (event.key === "Escape") setTitleDraft(null);
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        className="library-title"
                        data-session-row={session.id}
                        onMouseDown={(event) => {
                          if (event.shiftKey) event.preventDefault();
                        }}
                        onClick={(event) => {
                          if (event.ctrlKey || event.metaKey || event.shiftKey) pick(event, session.id);
                          else onOpenSession(session.id);
                        }}
                      >
                        <Icon name={modeIcon(session.capture_mode)} size={14} />
                        <span title={session.title}>{withoutTrailingDate(session.title)}</span>
                        {live ? <em className="library-live">{t("status.live")}</em> : null}
                      </button>
                    )}
                    <span className="library-tags">
                      {(session.tags ?? []).map((item) => (
                        <span key={item.id} className="library-tag">
                          {item.name}
                        </span>
                      ))}
                    </span>
                    <span className="library-date">
                      {session.deleted_at ? (
                        deletedAgo(session.deleted_at)
                      ) : (
                        <>
                          {when(session.started_at)} <small>{hour(session.started_at)}</small>
                        </>
                      )}
                    </span>
                    <span className="library-length is-num">
                      <span>{formatClock(session.duration_ms)}</span>
                      <SessionRowMenu
                        ref={(handle) => {
                          if (handle) menus.current.set(session.id, handle);
                          else menus.current.delete(session.id);
                        }}
                        session={session}
                        live={live}
                        busy={pendingIds.has(session.id)}
                        folders={folders}
                        onMove={(folderId) => moveMany([session.id], folderId)}
                        onRename={() => setTitleDraft({ id: session.id, value: session.title })}
                        onAction={(action) => void act([session.id], action)}
                      />
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
