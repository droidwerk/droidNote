import type { NoteTemplate } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { templateName } from "../../shared/lib/templates";

interface TemplatePickerProps {
  templates: NoteTemplate[];
  value: string | null;
  disabled?: boolean;
  compact?: boolean;
  onChange: (id: string | null) => void;
}

/** Template de nota: muda as seções que a IA usa para organizar a ata. */
export function TemplatePicker({ templates, value, disabled = false, compact = false, onChange }: TemplatePickerProps) {
  const t = useT();
  const notes = templates.filter((item) => item.kind === "note");
  return (
    <label className={compact ? "template-picker is-compact" : "template-picker"} title={t("templates.pickerHint")}>
      {compact ? null : <span>{t("templates.label")}</span>}
      <select
        className="select"
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">{compact ? `${t("templates.label")}: ${t("templates.auto")}` : t("templates.auto")}</option>
        {notes.map((item) => (
          <option key={item.id} value={item.id}>
            {templateName(item)}
          </option>
        ))}
      </select>
    </label>
  );
}
