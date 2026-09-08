import { useState } from "react";

import { api } from "../../shared/api/client";
import type { Tag } from "../../shared/api/types";
import { Button } from "../../shared/ui/primitives";

interface SessionTagsProps {
  sessionId: string;
  tags: Tag[];
  catalog: Tag[];
  onChange: (tags: Tag[]) => void;
}

export function SessionTags({ sessionId, tags, catalog, onChange }: SessionTagsProps) {
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
      <div className="session-tags-list">
        {tags.length === 0 ? <span className="muted">Sem pasta</span> : null}
        {tags.map((tag) => (
          <button
            key={tag.id}
            type="button"
            className="tag-chip on"
            disabled={busy}
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
            onClick={() => addExisting(tag)}
          >
            {tag.name}
          </button>
        ))}
        <input
          className="search"
          placeholder="Nova pasta (Aulas, Clientes…)"
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
          Adicionar
        </Button>
      </div>
    </div>
  );
}
