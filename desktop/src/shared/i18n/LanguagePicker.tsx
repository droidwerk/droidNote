import { CAPTURE_LANGUAGE_IDS, UI_LANGUAGES, type CaptureLanguage, type UiLanguage } from "./locales";
import { useI18n } from "./I18nProvider";

interface LanguagePickerProps {
  compact?: boolean;
  onPicked?: (id: UiLanguage) => void;
}

interface CaptureLanguagePickerProps {
  value: CaptureLanguage;
  onPicked: (id: CaptureLanguage) => void;
}

export function LanguagePicker({ compact = false, onPicked }: LanguagePickerProps) {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className={compact ? "lang-grid is-compact" : "lang-grid"}
      role="radiogroup"
      aria-label={t("languages.pickerAria")}
    >
      {UI_LANGUAGES.map((item) => (
        <button
          key={item.id}
          type="button"
          role="radio"
          aria-checked={locale === item.id}
          className={locale === item.id ? "theme-card is-selected" : "theme-card"}
          onClick={() => {
            setLocale(item.id);
            onPicked?.(item.id);
          }}
        >
          <strong>{item.native}</strong>
        </button>
      ))}
    </div>
  );
}

export function CaptureLanguagePicker({ value, onPicked }: CaptureLanguagePickerProps) {
  const { t } = useI18n();
  return (
    <div className="lang-grid is-capture" role="radiogroup" aria-label={t("languages.captureLabel")}>
      {CAPTURE_LANGUAGE_IDS.map((id) => {
        const selected = value === id;
        const label = id === "auto" ? t("languages.autoShort") : UI_LANGUAGES.find((item) => item.id === id)?.native ?? id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={selected}
            className={selected ? "theme-card is-selected" : "theme-card"}
            onClick={() => onPicked(id)}
          >
            <strong>{label}</strong>
            {id === "auto" ? <span>{t("languages.auto")}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
