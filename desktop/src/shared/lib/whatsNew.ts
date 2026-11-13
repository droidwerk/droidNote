import type { UiLanguage } from "../i18n";

/** Itens de "Novidades" por versão exata ("2.3.1") ou por major.minor ("2.3");
 *  cada id vira a chave `whatsNew.items.<id>`. A versão exata vence. */
export const WHATS_NEW: Record<string, readonly string[]> = {
  "2.3": ["chatMarkdown", "chatCitations", "chatModes", "chatSources", "exports"],
  "2.3.1": ["chatContext", "tour", "memoryFolder", "help", "readability"],
};

function clean(version: string): string {
  return version.trim().replace(/^v/i, "");
}

export function majorMinor(version: string): string {
  return clean(version).split(".").slice(0, 2).join(".");
}

export function whatsNewFor(version: string): readonly string[] {
  return WHATS_NEW[clean(version)] ?? WHATS_NEW[majorMinor(version)] ?? [];
}

/** Novidades a mostrar de `last` para `current`: a lista da versão exata quando a versão mudou;
 *  a de major.minor só quando o major.minor mudou (um patch sem lista própria não repete a anterior). */
export function newsBetween(last: string | null, current: string): readonly string[] {
  if (!current || (last && clean(last) === clean(current))) return [];
  const exact = WHATS_NEW[clean(current)];
  if (exact) return exact;
  if (last && majorMinor(last) === majorMinor(current)) return [];
  return WHATS_NEW[majorMinor(current)] ?? [];
}

export type OnboardingKind = "welcome" | "news" | null;

/** Decide o diálogo de abertura. Instalação nova = o assistente rodou nesta execução, ou nenhuma marca
 *  local e nenhuma conversa (install.ps1 pode pular o assistente). sessionCount null = não consultado. */
export function decideOnboarding({
  wizardRan,
  last,
  welcomeSeen,
  sessionCount,
  current,
}: {
  wizardRan: boolean;
  last: string | null;
  welcomeSeen: boolean;
  sessionCount: number | null;
  current: string;
}): OnboardingKind {
  if (wizardRan || (!last && !welcomeSeen && sessionCount === 0)) return welcomeSeen ? null : "welcome";
  // Sem versão anotada, quem já usava veio de antes deste aviso: conta como atualização.
  if (newsBetween(last, current).length > 0) return "news";
  return null;
}

export const WELCOME_KEY = "droidnote.welcomeSeen";
export const LAST_VERSION_KEY = "droidnote.lastVersion";

export function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* modo privado: o aviso pode voltar, nada quebra */
  }
}

export const RELEASES_PAGE = "https://github.com/droidwerk/droidNote/releases";
export const ISSUES_PAGE = "https://github.com/droidwerk/droidNote/issues";
export const SECRETS_SOURCE = "https://github.com/droidwerk/droidNote/blob/main/backend/app/core/secrets.py";

/** O site só tem pt, en e de; o resto cai em en. Fixo de propósito: não ler os idiomas do site. */
export function siteUrl(locale: UiLanguage, page: "" | "about" | "products" | "droidnote" = ""): string {
  const loc = locale === "pt" || locale === "de" ? locale : "en";
  return `https://www.droidwerk.com.br/${loc}${page ? `/${page}` : ""}`;
}
