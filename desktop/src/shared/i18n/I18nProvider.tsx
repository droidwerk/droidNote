import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { bcp47, isUiLanguage, STORAGE_KEY, type UiLanguage } from "./locales";
import { bindI18n } from "./runtime";
import { translate } from "./translate";
import type { MessagePath } from "./types";

export type TranslateFn = (key: MessagePath | string, vars?: Record<string, string | number>) => string;

interface I18nContextValue {
  locale: UiLanguage;
  setLocale: (locale: UiLanguage) => void;
  t: TranslateFn;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function readStoredLocale(): UiLanguage {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isUiLanguage(stored)) return stored;
  } catch {
    /* private mode */
  }
  return "pt";
}

function persistLocale(locale: UiLanguage): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* private mode */
  }
  document.documentElement.lang = bcp47(locale);
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<UiLanguage>(() => readStoredLocale());

  const t = useCallback<TranslateFn>(
    (key, vars) => translate(locale, key, vars),
    [locale],
  );

  useEffect(() => {
    persistLocale(locale);
    bindI18n(locale, (key, vars) => translate(locale, key, vars));
  }, [locale]);

  const setLocale = useCallback((next: UiLanguage) => {
    setLocaleState(next);
  }, []);

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return createElement(I18nContext.Provider, { value }, children);
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n precisa de I18nProvider");
  }
  return context;
}

export function useT(): TranslateFn {
  return useI18n().t;
}
