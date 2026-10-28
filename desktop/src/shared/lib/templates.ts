import type { NoteTemplate } from "../api/types";
import { tr } from "../i18n/runtime";

/** Nome exibido: embutidos vêm traduzidos pelo id; os da pessoa, como ela escreveu. */
export function templateName(template: Pick<NoteTemplate, "id" | "name" | "builtin">): string {
  if (!template.builtin) return template.name;
  const key = `templates.builtin_names.${template.id}`;
  const label = tr(key);
  return label === key ? template.name : label;
}
