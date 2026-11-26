// Lógica pura das ações em lote (sem React): o hook useSessionActions só injeta as dependências.
// Imports só de tipo, para rodar em `node --test` sem framework.
import type { Session, SessionBulkAction, SessionBulkResult } from "../../shared/api/types";
import type { ConfirmOptions } from "../../shared/ui/ConfirmDialog";
import type { ToastInput } from "../../shared/ui/Toast";

export type Target = Pick<Session, "id" | "title">;

export const UNDO_MS = 10_000;
/** SessionBulkIn aceita no máximo 500 ids por chamada. */
export const BULK_CHUNK = 500;
const TRASH_DAYS = 30;
const DAY_MS = 86_400_000;
const FAIL_KEY = {
  archive: "archive.archiveFail",
  unarchive: "archive.restoreFail",
  trash: "archive.deleteFail",
  restore: "archive.restoreFail",
  purge: "archive.deleteFail",
} as const satisfies Record<SessionBulkAction, string>;
const INVERSE: Partial<Record<SessionBulkAction, SessionBulkAction>> = { archive: "unarchive", trash: "restore" };

/** Dias inteiros desde `iso` (0 no mesmo dia). */
export function daysSince(iso: string, now = Date.now()): number {
  return Math.max(0, Math.floor((now - Date.parse(iso)) / DAY_MS));
}

/** Dias até a lixeira apagar de vez (nunca negativo). */
export function daysLeftInTrash(deletedAt: string, now = Date.now()): number {
  return Math.max(0, TRASH_DAYS - daysSince(deletedAt, now));
}

export interface SessionActionDeps {
  bulk: (ids: string[], action: SessionBulkAction) => Promise<SessionBulkResult>;
  onChanged: () => Promise<unknown> | void;
  liveSessionId: string | null;
  t: (key: string, values?: Record<string, string | number>) => string;
  plural: (count: number) => string;
  push: (toast: ToastInput) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

/** Manda em pedaços de BULK_CHUNK, em sequência, e junta os resultados. */
export async function bulkChunked(
  bulk: SessionActionDeps["bulk"],
  ids: string[],
  action: SessionBulkAction,
): Promise<SessionBulkResult> {
  const merged: SessionBulkResult = { done: [], failed: [] };
  for (let start = 0; start < ids.length; start += BULK_CHUNK) {
    const part = await bulk(ids.slice(start, start + BULK_CHUNK), action);
    merged.done.push(...part.done);
    merged.failed.push(...part.failed);
  }
  return merged;
}

/**
 * Arquivar, lixeira, restaurar e apagar de vez com o mesmo aviso em todo lugar.
 * A ação vai ao servidor na hora; "Desfazer" (10 s, Ctrl+Z) chama a ação inversa.
 * A sessão gravando agora nunca entra: o aviso diz que ficou de fora.
 */
export function createSessionActions({ bulk, onChanged, liveSessionId, t, plural, push, confirm }: SessionActionDeps) {
  const apply = async (targets: Target[], action: SessionBulkAction): Promise<SessionBulkResult | null> => {
    const skippedLive = targets.some((item) => item.id === liveSessionId);
    const ids = targets.filter((item) => item.id !== liveSessionId).map((item) => item.id);
    if (!ids.length) {
      if (skippedLive) push({ tone: "info", title: t("archive.liveLocked") });
      return null;
    }
    let result: SessionBulkResult;
    try {
      result = await bulkChunked(bulk, ids, action);
    } catch {
      push({ tone: "error", title: t(FAIL_KEY[action]) });
      return null;
    }
    await onChanged();
    if (result.failed.length) {
      push({
        tone: "error",
        title: ids.length > 1 ? t("archive.partialFail", { failed: result.failed.length, count: ids.length }) : t(FAIL_KEY[action]),
      });
    }
    const inverse = INVERSE[action];
    const done = result.done;
    if (inverse && done.length) {
      const one = done.length === 1 ? targets.find((item) => item.id === done[0]) : undefined;
      const title = one
        ? t(action === "archive" ? "archive.archivedOne" : "archive.trashedOne", { title: one.title })
        : t(`${action === "archive" ? "archive.archivedMany" : "archive.trashedMany"}.${plural(done.length)}`, { count: done.length });
      push({
        key: "session-undo",
        tone: "success",
        title,
        description: skippedLive ? t("archive.liveSkipped") : undefined,
        durationMs: UNDO_MS,
        action: {
          label: t("archive.undo"),
          undo: true,
          onClick: () => {
            void bulkChunked(bulk, done, inverse)
              .then(async () => {
                await onChanged();
                push({ key: "session-undo", tone: "success", title: t("archive.undone"), durationMs: 3000 });
              })
              .catch(() => push({ tone: "error", title: t("archive.restoreFail") }));
          },
        },
      });
    }
    return result;
  };

  /** Único caminho com confirmação: apagar de vez some com linhas e áudio. `all` = esvaziar a lixeira. */
  const purge = async (targets: Target[], all = false): Promise<SessionBulkResult | null> => {
    if (!targets.length) return null;
    const ok = await confirm({
      title: all
        ? t("archive.purgeTitleAll")
        : targets.length === 1
          ? t("archive.purgeTitleOne", { title: targets[0]?.title ?? "" })
          : t(`archive.purgeTitleMany.${plural(targets.length)}`, { count: targets.length }),
      description: t("archive.purgeBody"),
      confirmLabel: t("archive.purge"),
      tone: "danger",
    });
    return ok ? apply(targets, "purge") : null;
  };

  return { apply, purge };
}
