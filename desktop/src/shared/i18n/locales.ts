export const UI_LANGUAGE_IDS = ["pt", "en", "es", "it", "de", "fr", "ru"] as const;

export type UiLanguage = (typeof UI_LANGUAGE_IDS)[number];

export type CaptureLanguage = UiLanguage | "auto";

export const UI_LANGUAGES: readonly { id: UiLanguage; native: string; bcp47: string }[] = [
  { id: "pt", native: "Português", bcp47: "pt-BR" },
  { id: "en", native: "English", bcp47: "en" },
  { id: "es", native: "Español", bcp47: "es" },
  { id: "it", native: "Italiano", bcp47: "it" },
  { id: "de", native: "Deutsch", bcp47: "de" },
  { id: "fr", native: "Français", bcp47: "fr" },
  { id: "ru", native: "Русский", bcp47: "ru" },
];

export const CAPTURE_LANGUAGE_IDS: readonly CaptureLanguage[] = [
  ...UI_LANGUAGE_IDS,
  "auto",
];

export const STORAGE_KEY = "droidnote.ui_language";

export function isUiLanguage(value: string | null | undefined): value is UiLanguage {
  return UI_LANGUAGE_IDS.includes(value as UiLanguage);
}

export function isCaptureLanguage(value: string | null | undefined): value is CaptureLanguage {
  return CAPTURE_LANGUAGE_IDS.includes(value as CaptureLanguage);
}

export function bcp47(locale: UiLanguage): string {
  return UI_LANGUAGES.find((item) => item.id === locale)?.bcp47 ?? "pt-BR";
}

export function pluralForm(locale: UiLanguage, count: number): "one" | "few" | "many" {
  if (locale === "ru") {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return "one";
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "few";
    return "many";
  }
  return count === 1 ? "one" : "many";
}
