import { pt } from "./catalogs/pt";
import { en } from "./catalogs/en";
import { es } from "./catalogs/es";
import { it } from "./catalogs/it";
import { de } from "./catalogs/de";
import { fr } from "./catalogs/fr";
import { ru } from "./catalogs/ru";
import type { UiLanguage } from "./locales";
import type { MessagePath, Messages } from "./types";

const CATALOGS: Record<UiLanguage, Messages> = { pt, en, es, it, de, fr, ru };

export function catalogFor(locale: UiLanguage): Messages {
  return CATALOGS[locale] ?? pt;
}

export function lookup(messages: Messages, path: string): string | undefined {
  let node: unknown = messages;
  for (const part of path.split(".")) {
    if (!node || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = vars[name];
    return value === undefined ? `{${name}}` : String(value);
  });
}

export function translate(
  locale: UiLanguage,
  path: MessagePath | string,
  vars?: Record<string, string | number>,
): string {
  const primary = lookup(catalogFor(locale), path) ?? lookup(pt, path);
  if (!primary) return path;
  return interpolate(primary, vars);
}
