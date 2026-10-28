import { useCallback, useEffect, useState } from "react";

import { api } from "../../shared/api/client";
import type { NoteTemplate } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { templateName } from "../../shared/lib/templates";
import { useConfirm } from "../../shared/ui/ConfirmDialog";
import { Button, Card } from "../../shared/ui/primitives";

interface Draft {
  id: string | null;
  kind: "note" | "recipe";
  name: string;
  body: string;
}

const EMPTY: Draft = { id: null, kind: "note", name: "", body: "" };

export function TemplateManager({ onChanged }: { onChanged?: () => void }) {
  const t = useT();
  const confirm = useConfirm();
  const [items, setItems] = useState<NoteTemplate[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setItems(await api.templates());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!draft) return;
    setError(null);
    try {
      if (draft.id) {
        await api.updateTemplate(draft.id, { name: draft.name, body: draft.body });
      } else {
        await api.createTemplate({ kind: draft.kind, name: draft.name, body: draft.body });
      }
      setDraft(null);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("settings.saveFail"));
    }
  };

  const remove = async (item: NoteTemplate) => {
    const ok = await confirm({
      title: t("templates.deleteTitle", { name: templateName(item) }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    await api.deleteTemplate(item.id);
    await load();
    onChanged?.();
  };

  const section = (kind: "note" | "recipe") => (
    <Card className="settings-card settings-card-wide">
      <div className="template-head">
        <div>
          <h2>{kind === "note" ? t("templates.notesTitle") : t("recipes.title")}</h2>
          <p className="muted">{kind === "note" ? t("templates.notesHelp") : t("recipes.help")}</p>
        </div>
        <Button size="sm" variant="primary" onClick={() => setDraft({ ...EMPTY, kind })}>
          {t("templates.new")}
        </Button>
      </div>
      {draft && draft.kind === kind ? (
        <div className="template-form">
          <input
            className="input"
            value={draft.name}
            placeholder={t("templates.namePlaceholder")}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <textarea
            className="input template-body"
            value={draft.body}
            rows={6}
            placeholder={kind === "note" ? t("templates.bodyPlaceholder") : t("recipes.bodyPlaceholder")}
            onChange={(event) => setDraft({ ...draft, body: event.target.value })}
          />
          {error ? <p className="banner">{error}</p> : null}
          <div className="row">
            <Button variant="primary" disabled={!draft.name.trim() || !draft.body.trim()} onClick={() => void save()}>
              {t("common.save")}
            </Button>
            <Button onClick={() => setDraft(null)}>{t("common.cancel")}</Button>
          </div>
        </div>
      ) : null}
      <ul className="template-list">
        {items
          .filter((item) => item.kind === kind)
          .map((item) => (
            <li key={item.id}>
              <div className="template-copy">
                <strong>
                  {templateName(item)}
                  {item.builtin ? <span className="voice-flag">{t("templates.builtin")}</span> : null}
                </strong>
                <p>{item.body.split("\n").join(" · ")}</p>
              </div>
              <div className="people-actions">
                <Button
                  size="sm"
                  variant="quiet"
                  onClick={() => setDraft({ id: null, kind, name: `${templateName(item)} (2)`, body: item.body })}
                >
                  {t("templates.duplicate")}
                </Button>
                {!item.builtin ? (
                  <>
                    <Button size="sm" variant="quiet" onClick={() => setDraft({ id: item.id, kind, name: item.name, body: item.body })}>
                      {t("transcript.edit")}
                    </Button>
                    <Button size="sm" onClick={() => void remove(item)}>
                      {t("common.delete")}
                    </Button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
      </ul>
    </Card>
  );

  return (
    <>
      {section("note")}
      {section("recipe")}
    </>
  );
}
