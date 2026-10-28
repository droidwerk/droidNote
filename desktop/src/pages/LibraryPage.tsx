import { useMemo, useState, type DragEvent } from "react";

import { api } from "../shared/api/client";
import type { Session, Tag } from "../shared/api/types";
import { useI18n } from "../shared/i18n";
import { bcp47 } from "../shared/i18n/locales";
import { formatClock } from "../shared/lib/format";
import { useFlag } from "../shared/lib/useFlag";
import { InfoTip } from "../shared/ui/InfoTip";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { Icon } from "../shared/ui/Icon";
import { useToast } from "../shared/ui/Toast";
import { modeIcon } from "../features/command/CommandPalette";

const DRAG_TYPE = "application/x-droidnote-session";

type FolderFilter = "all" | "none" | string;
type Sort = "recent" | "oldest" | "longest" | "title";

interface LibraryPageProps {
  sessions: Session[];
  folders: Tag[];
  liveSessionId: string | null;
  onOpenSession: (sessionId: string) => void;
  onChanged: () => Promise<void> | void;
}

/** Conversas: pastas à esquerda, lista à direita, seleção para mover ou apagar várias de uma vez. */
export function LibraryPage({ sessions, folders, liveSessionId, onOpenSession, onChanged }: LibraryPageProps) {
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
    const list = sessions.filter((session) => {
      const tags = session.tags ?? [];
      if (filter === "none" && tags.length) return false;
      if (filter !== "all" && filter !== "none" && !tags.some((tag) => tag.id === filter)) return false;
      return !needle || session.title.toLowerCase().includes(needle);
    });
    const by: Record<Sort, (a: Session, b: Session) => number> = {
      recent: (a, b) => b.started_at.localeCompare(a.started_at),
      oldest: (a, b) => a.started_at.localeCompare(b.started_at),
      longest: (a, b) => b.duration_ms - a.duration_ms,
      title: (a, b) => a.title.localeCompare(b.title, bcp47(locale)),
    };
    return [...list].sort(by[sort]);
  }, [sessions, filter, query, sort, locale]);

  const allChecked = visible.length > 0 && visible.every((session) => selected.has(session.id));
  const toggleAll = () =>
    setSelected(allChecked ? new Set() : new Set(visible.map((session) => session.id)));
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
      await onChanged();
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

  const deleteMany = async () => {
    const ids = [...selected].filter((id) => id !== liveSessionId);
    if (!ids.length) return;
    const ok = await confirm({
      title: t("library.deleteTitle", { count: ids.length }),
      description: t("library.deleteBody"),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    await run(async () => {
      await Promise.all(ids.map((id) => api.deleteSession(id)));
      setSelected(new Set());
    });
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
      if (!event.dataTransfer.types.includes(DRAG_TYPE) || target === "all") return;
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
      void moveMany(ids, target === "none" ? null : target);
    },
  });

  const tag = bcp47(locale);
  const when = (iso: string) =>
    new Date(iso).toLocaleDateString(tag, { day: "2-digit", month: "short", year: new Date(iso).getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
  const hour = (iso: string) => new Date(iso).toLocaleTimeString(tag, { hour: "2-digit", minute: "2-digit" });
  const filterName =
    filter === "all" ? t("folders.all") : filter === "none" ? t("folders.noFolder") : folders.find((item) => item.id === filter)?.name ?? "";

  return (
    <div className="page library">
      <header className="page-head">
        <div className="page-head-copy">
          <h1>{t("library.title")}</h1>
        </div>
      </header>

      <div className={foldersCollapsed ? "library-body is-folders-collapsed" : "library-body"}>
        <nav className="library-folders" aria-label={t("folders.title")}>
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
          ) : null}
        </nav>

        <section className="library-main">
          <div className="library-toolbar">
            {selected.size ? (
              <div className="library-bulk" role="toolbar">
                <strong>{t("library.selected", { count: selected.size })}</strong>
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
                <button type="button" className="tool-btn is-danger" disabled={busy} onClick={() => void deleteMany()}>
                  <Icon name="trash" size={14} />
                  <span>{t("common.delete")}</span>
                </button>
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

          {visible.length === 0 ? (
            <div className="library-empty">
              <strong>{query ? t("library.noMatch") : t("library.emptyFolder")}</strong>
              {!query && filter !== "all" ? <small>{t("library.emptyFolderHint")}</small> : null}
            </div>
          ) : (
            <div className="library-table" role="table">
              <div className="library-row library-row-head" role="row">
                <label className="library-check" role="columnheader">
                  <input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label={t("library.selectAll")} />
                </label>
                <span role="columnheader">{t("library.colTitle")}</span>
                <span role="columnheader">{t("folders.title")}</span>
                <span role="columnheader">{t("library.colDate")}</span>
                <span role="columnheader" className="is-num">{t("library.colLength")}</span>
              </div>
              {visible.map((session) => {
                const checked = selected.has(session.id);
                const live = session.id === liveSessionId;
                return (
                  <div
                    key={session.id}
                    role="row"
                    className={checked ? "library-row is-checked" : "library-row"}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData(DRAG_TYPE, session.id);
                      event.dataTransfer.setData("text/plain", session.title);
                    }}
                  >
                    <label className="library-check">
                      <input type="checkbox" checked={checked} onChange={() => toggle(session.id)} aria-label={session.title} />
                    </label>
                    <button type="button" className="library-title" onClick={() => onOpenSession(session.id)}>
                      <Icon name={modeIcon(session.capture_mode)} size={14} />
                      <span>{session.title}</span>
                      {live ? <em className="library-live">{t("status.live")}</em> : null}
                    </button>
                    <span className="library-tags">
                      {(session.tags ?? []).map((item) => (
                        <span key={item.id} className="library-tag">
                          {item.name}
                        </span>
                      ))}
                    </span>
                    <span className="library-date">
                      {when(session.started_at)} <small>{hour(session.started_at)}</small>
                    </span>
                    <span className="library-length is-num">{formatClock(session.duration_ms)}</span>
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
