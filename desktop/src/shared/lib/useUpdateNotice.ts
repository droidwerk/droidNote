import { useEffect, useState } from "react";

import { useT } from "../i18n";
import { useConfirm } from "../ui/ConfirmDialog";
import { useToast } from "../ui/Toast";
import { findAppUpdate, rememberSkippedUpdate, UPDATE_COMMAND } from "./appUpdate";
import { copyToClipboard } from "./format";
import { openExternal } from "./openExternal";

/** Mostra o aviso de nova versão. Devolve true quando o aviso já foi resolvido (ou não havia),
 *  para que outro diálogo (boas-vindas, novidades) nunca abra por cima dele. */
export function useUpdateNotice(enabled: boolean): boolean {
  const t = useT();
  const [settled, setSettled] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const run = async () => {
      let current = "";
      try {
        const { getVersion } = await import("@tauri-apps/api/app");
        current = await getVersion();
      } catch {
        return;
      }
      const notice = await findAppUpdate(current);
      if (!notice || cancelled) return;
      const accepted = await confirm({
        title: t("update.title"),
        description: t("update.body", { latest: notice.version, current: notice.current }),
        confirmLabel: t("update.download"),
        cancelLabel: t("update.later"),
        extraAction: {
          label: t("update.copyCommand"),
          onClick: () => {
            void copyToClipboard(UPDATE_COMMAND).then((ok) =>
              toast.push({
                tone: ok ? "success" : "error",
                title: ok ? t("update.commandCopied") : t("update.copyFail"),
                description: ok ? t("update.commandCopiedHint") : undefined,
              }),
            );
          },
        },
      });
      if (cancelled) return;
      if (accepted) {
        await openExternal(notice.downloadUrl);
        return;
      }
      rememberSkippedUpdate(notice.version);
    };
    void run().finally(() => {
      if (!cancelled) setSettled(true);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, confirm, t, toast]);

  return settled;
}
