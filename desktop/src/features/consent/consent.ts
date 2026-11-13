import { api } from "../../shared/api/client";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";
import { copyToClipboard } from "../../shared/lib/format";

/** Texto do aviso: o da pessoa (Configurações) ou o padrão no idioma da interface.
 *  Com transcrição na nuvem, o padrão diz que o áudio passa pela OpenAI. */
export function consentText(custom: string | null | undefined, t: TranslateFn, cloud = false): string {
  return custom?.trim() || t(cloud ? "consent.defaultCloud" : "consent.default");
}

/** Copia o aviso de gravação para colar no chat da reunião. */
export async function copyConsent(t: TranslateFn): Promise<boolean> {
  let custom = "";
  let cloud = false;
  try {
    const settings = await api.getSettings();
    custom = settings.consent_message ?? "";
    cloud = settings.provider === "openai";
  } catch {
    /* sem backend: usa o padrão */
  }
  return copyToClipboard(consentText(custom, t, cloud));
}
