import type { UiLanguage } from "./locales";
import { bcp47 } from "./locales";

type Translate = (key: string, vars?: Record<string, string | number>) => string;

let currentLocale: UiLanguage = "pt";
let translate: Translate = (key) => key;

export function bindI18n(locale: UiLanguage, fn: Translate): void {
  currentLocale = locale;
  translate = fn;
  if (typeof document !== "undefined") {
    document.documentElement.lang = bcp47(locale);
  }
}

export function tr(key: string, vars?: Record<string, string | number>): string {
  return translate(key, vars);
}

export function currentUiLanguage(): UiLanguage {
  return currentLocale;
}
