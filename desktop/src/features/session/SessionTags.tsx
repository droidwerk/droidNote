import { useState } from "react";

import { api } from "../../shared/api/client";
import type { Tag } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Button } from "../../shared/ui/primitives";

interface SessionTagsProps {
  sessionId: string;
  tags: Tag[];
  catalog: Tag[];
  onChange: (tags: Tag[]) => void;
}

export function SessionTags({ sessionId, tags, catalog, onChange }: SessionTagsProps) {
  const t = useT();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const assigned = new Set(tags.map((item) => item.id));
  const available = catalog.filter((item) => !assigned.has(item.id));

  const persist = async (nextIds: string[]) => {
    setBusy(true);
    try {
      onChange(await api.setSessionTags(sessionId, nextIds));
    } finally {
      setBusy(false);
    }
  };

  const addExisting = (tag: Tag) => {
    void persist([...tags.map((item) => item.id), tag.id]);
  };

  const create = async () => {
    const name = draft.trim();
    if (!name) return;
    setBusy(true);
    try {
      const tag = await api.createTag(name);
      setDraft("");
      onChange(await api.setSessionTags(sessionId, [...tags.map((item) => item.id), tag.id]));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="session-tags">
      <span className="session-tags-label">{t("folders.sessionFolders")}</span>
      <div className="session-tags-list">
        {tags.length === 0 ? <span className="muted">{t("folders.noFolder")}</span> : null}
        {tags.map((tag) => (
          <button
            key={tag.id}
            type="button"
            className="tag-chip on"
            disabled={busy}
            title={t("folders.removeFrom", { name: tag.name })}
            onClick={() => void persist(tags.filter((item) => item.id !== tag.id).map((item) => item.id))}
          >
            {tag.name}
          </button>
        ))}
      </div>
      <div className="session-tags-add">
        {available.map((tag) => (
          <button
            key={tag.id}
            type="button"
            className="tag-chip"
            disabled={busy}
            title={t("folders.addTo", { name: tag.name })}
            onClick={() => addExisting(tag)}
          >
            {tag.name}
          </button>
        ))}
        <input
          className="search"
          placeholder={t("folders.newFolderPlaceholder")}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void create();
            }
          }}
        />
        <Button size="sm" variant="quiet" disabled={busy || !draft.trim()} onClick={() => void create()}>
          {t("common.add")}
        </Button>
      </div>
    </div>
  );
}
