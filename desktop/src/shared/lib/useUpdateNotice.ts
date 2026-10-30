import { useEffect } from "react";

import { useT } from "../i18n";
import { useConfirm } from "../ui/ConfirmDialog";
import { useToast } from "../ui/Toast";
import { findAppUpdate, rememberSkippedUpdate, UPDATE_COMMAND } from "./appUpdate";
import { copyToClipboard } from "./format";
import { openExternal } from "./openExternal";

export function useUpdateNotice(enabled: boolean): void {
  const t = useT();
  const confirm = useConfirm();
  const toast = useToast();

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void (async () => {
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
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled, confirm, t, toast]);
}
