import { useMemo } from "react";

import { api } from "../../shared/api/client";
import { pluralForm, useI18n } from "../../shared/i18n";
import { useConfirm } from "../../shared/ui/ConfirmDialog";
import { useToast } from "../../shared/ui/Toast";
import { createSessionActions } from "./sessionActions";

export { daysLeftInTrash, daysSince } from "./sessionActions";

/** Ações de arquivo e lixeira com aviso, Desfazer e confirmação (lógica em sessionActions.ts). */
export function useSessionActions(onChanged: () => Promise<unknown> | void, liveSessionId: string | null) {
  const { t, locale } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();

  return useMemo(
    () =>
      createSessionActions({
        bulk: (ids, action) => api.bulkSessions(ids, action),
        onChanged,
        liveSessionId,
        t: t as (key: string, values?: Record<string, string | number>) => string,
        plural: (count) => pluralForm(locale, count),
        push: toast.push,
        confirm,
      }),
    [onChanged, liveSessionId, t, locale, toast, confirm],
  );
}
