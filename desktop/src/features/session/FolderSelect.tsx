import { useState } from "react";

import { api } from "../../shared/api/client";
import type { Tag } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

interface FolderSelectProps {
  sessionId: string;
  tags: Tag[];
  catalog: Tag[];
  onChange: (tags: Tag[]) => void;
}

const NEW = "__new";

/** Pasta da conversa: um seletor só, com "Nova pasta…" no fim da lista. */
export function FolderSelect({ sessionId, tags, catalog, onChange }: FolderSelectProps) {
  const t = useT();
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const current = tags[0]?.id ?? "";

  const assign = async (folderId: string | null) => {
    setBusy(true);
    try {
      onChange(await api.setSessionTags(sessionId, folderId ? [folderId] : []));
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    const name = draft.trim();
    setCreating(false);
    setDraft("");
    if (!name) return;
    setBusy(true);
    try {
      const folder = await api.createTag(name);
      onChange(await api.setSessionTags(sessionId, [folder.id]));
    } finally {
      setBusy(false);
    }
  };

  if (creating) {
    return (
      <input
        className="folder-select-input"
        autoFocus
        maxLength={40}
        value={draft}
        placeholder={t("folders.name")}
        aria-label={t("folders.newName")}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => void create()}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setDraft("");
            setCreating(false);
          }
        }}
      />
    );
  }

  return (
    <label className="folder-select" title={t("folders.moveTo")}>
      <Icon name="folder" size={14} />
      <select
        value={current}
        disabled={busy}
        aria-label={t("folders.moveTo")}
        onChange={(event) => {
          const value = event.target.value;
          if (value === NEW) setCreating(true);
          else void assign(value || null);
        }}
      >
        <option value="">{t("folders.noFolder")}</option>
        {catalog.map((folder) => (
          <option key={folder.id} value={folder.id}>
            {folder.name}
          </option>
        ))}
        <option value={NEW}>{t("library.newFolder")}</option>
      </select>
    </label>
  );
}
