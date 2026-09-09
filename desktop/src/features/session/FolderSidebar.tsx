import { useState, type DragEvent, type FormEvent } from "react";

import type { Tag } from "../../shared/api/types";
import { useConfirm } from "../../shared/ui/ConfirmDialog";

interface FolderSidebarProps {
  folders: Tag[];
  selectedId: string | null;
  sessionCount: number;
  countByFolder: ReadonlyMap<string, number>;
  onSelect: (id: string | null) => void;
  onCreate: (name: string) => Promise<void>;
  onDelete: (folder: Tag) => Promise<void>;
  onMoveSession: (sessionId: string, folderId: string) => Promise<void>;
}

export function FolderSidebar({
  folders,
  selectedId,
  sessionCount,
  countByFolder,
  onSelect,
  onCreate,
  onDelete,
  onMoveSession,
}: FolderSidebarProps) {
  const [draft, setDraft] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = draft.trim();
    if (!name || creating) return;
    setCreating(true);
    setError(null);
    try {
      await onCreate(name);
      setDraft("");
      setCreateOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar a pasta.");
    } finally {
      setCreating(false);
    }
  };

  const remove = async (folder: Tag) => {
    const count = countByFolder.get(folder.id) ?? 0;
    const ok = await confirm({
      title: `Apagar a pasta “${folder.name}”?`,
      description: count
        ? `${count} conversa${count === 1 ? "" : "s"} continuará no DroidNote, sem esta pasta.`
        : undefined,
      confirmLabel: "Apagar",
      tone: "danger",
    });
    if (!ok) return;
    setBusyId(folder.id);
    setError(null);
    try {
      await onDelete(folder);
      setMenuOpenId(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível apagar a pasta.");
    } finally {
      setBusyId(null);
    }
  };

  const dropSession = async (event: DragEvent<HTMLDivElement>, folder: Tag) => {
    event.preventDefault();
    const sessionId = event.dataTransfer.getData("application/x-droidnote-session");
    setDropTargetId(null);
    if (!sessionId) return;
    setBusyId(folder.id);
    setError(null);
    try {
      await onMoveSession(sessionId, folder.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível mover a conversa.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="folder-sidebar">
      <div className="folder-heading">
        <span>Pastas</span>
        <button
          type="button"
          className="folder-add"
          aria-label="Criar pasta"
          aria-expanded={createOpen}
          title="Criar pasta"
          onClick={() => setCreateOpen((current) => !current)}
        >
          <PlusIcon />
        </button>
      </div>

      {createOpen ? (
        <form className="folder-create" onSubmit={(event) => void create(event)}>
          <input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Nome da pasta"
            aria-label="Nome da nova pasta"
            disabled={creating}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setCreateOpen(false);
                setDraft("");
              }
            }}
          />
          <button type="submit" disabled={creating || !draft.trim()}>
            {creating ? "…" : "Criar"}
          </button>
        </form>
      ) : null}

      <div className="folder-list" aria-label="Pastas">
        <button
          type="button"
          className={selectedId === null ? "folder-row folder-all is-selected" : "folder-row folder-all"}
          aria-current={selectedId === null ? "true" : undefined}
          onClick={() => onSelect(null)}
        >
          <FolderIcon />
          <span>Todas as conversas</span>
          <small>{sessionCount}</small>
        </button>

        {folders.map((folder) => (
          <div
            className={[
              "folder-entry",
              selectedId === folder.id ? "is-selected" : "",
              dropTargetId === folder.id ? "is-drop-target" : "",
            ].filter(Boolean).join(" ")}
            key={folder.id}
            onDragEnter={(event) => {
              event.preventDefault();
              setDropTargetId(folder.id);
            }}
            onDragOver={(event) => {
              if (!event.dataTransfer.types.includes("application/x-droidnote-session")) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
            }}
            onDragLeave={(event) => {
              const nextTarget = event.relatedTarget;
              if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) return;
              setDropTargetId(null);
            }}
            onDrop={(event) => void dropSession(event, folder)}
          >
            <div className="folder-entry-line">
              <button
                type="button"
                className="folder-row"
                aria-current={selectedId === folder.id ? "true" : undefined}
                onClick={() => onSelect(folder.id)}
                disabled={busyId === folder.id}
              >
                <FolderIcon />
                <span>{folder.name}</span>
                <small>{countByFolder.get(folder.id) ?? 0}</small>
              </button>
              <button
                type="button"
                className="sidebar-more"
                aria-label={`Opções da pasta ${folder.name}`}
                aria-expanded={menuOpenId === folder.id}
                title="Mais opções"
                onClick={() => setMenuOpenId((current) => current === folder.id ? null : folder.id)}
              >
                <MoreIcon />
              </button>
            </div>
            {menuOpenId === folder.id ? (
              <div className="folder-action-menu">
                <button type="button" disabled={busyId === folder.id} onClick={() => void remove(folder)}>
                  Apagar pasta
                </button>
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {folders.length > 0 ? <p className="folder-hint">Arraste uma conversa para uma pasta.</p> : null}
      {error ? <p className="folder-error" role="alert">{error}</p> : null}
    </div>
  );
}

function FolderIcon() {
  return (
    <svg className="folder-icon" viewBox="0 0 20 20" fill="none" aria-hidden>
      <path d="M2.75 5.25h5l1.5 1.75h8v7.25a1.5 1.5 0 0 1-1.5 1.5h-11a2 2 0 0 1-2-2v-8.5Z" />
      <path d="M2.75 7h14.5" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden>
      <path d="M10 4.5v11M4.5 10h11" />
    </svg>
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
