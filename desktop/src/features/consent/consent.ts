import { api } from "../../shared/api/client";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";
import { copyToClipboard } from "../../shared/lib/format";

/** Texto do aviso: o da pessoa (Configurações) ou o padrão no idioma da interface. */
export function consentText(custom: string | null | undefined, t: TranslateFn): string {
  return custom?.trim() || t("consent.default");
}

/** Copia o aviso de gravação para colar no chat da reunião. */
export async function copyConsent(t: TranslateFn): Promise<boolean> {
  let custom = "";
  try {
    custom = (await api.getSettings()).consent_message ?? "";
  } catch {
    /* sem backend: usa o padrão */
  }
  return copyToClipboard(consentText(custom, t));
}
