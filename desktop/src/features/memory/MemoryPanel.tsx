import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../shared/api/client";
import type { Memory } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatDate } from "../../shared/lib/format";
import { AiThinking } from "../../shared/ui/AiThinking";
import { Icon } from "../../shared/ui/Icon";
import { InfoTip } from "../../shared/ui/InfoTip";
import { Button } from "../../shared/ui/primitives";

interface MemoryPanelProps {
  sessionId: string;
  /** Muda quando a ata, as tarefas ou a comparação em segundo plano mudam. */
  revision?: number;
  /** Sem motor de IA pronto, a comparação não é oferecida. */
  aiReady?: boolean;
  onOpenSession?: (sessionId: string) => void;
  onTasksChanged?: () => void;
}

/** Memória da série: o fio das reuniões anteriores e o que mudou desde a última. */
export function MemoryPanel({ sessionId, revision = 0, aiReady = true, onOpenSession, onTasksChanged }: MemoryPanelProps) {
  const t = useT();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const autoCompared = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMemory(await api.memory(sessionId));
    } catch {
      setMemory(null);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  const compare = useCallback(
    async (force = false) => {
      setComparing(true);
      setError(null);
      try {
        setMemory(await api.compareMemory(sessionId, force));
        onTasksChanged?.();
      } catch (err) {
        setError(err instanceof Error ? err.message : t("memory.failed"));
      } finally {
        setComparing(false);
      }
    },
    [sessionId, onTasksChanged, t],
  );

  // Ata pronta e ainda sem comparação: compara sozinho, uma vez por sessão.
  useEffect(() => {
    if (!memory || !aiReady || comparing) return;
    if (memory.mode === "after" && !memory.generated && autoCompared.current !== sessionId) {
      autoCompared.current = sessionId;
      void compare();
    }
  }, [memory, aiReady, comparing, sessionId, compare]);

  const markDone = async (taskId: string) => {
    setDone((current) => ({ ...current, [taskId]: true }));
    try {
      await api.updateTask(taskId, { done: true });
      onTasksChanged?.();
    } catch {
      setDone((current) => ({ ...current, [taskId]: false }));
    }
  };

  if (!memory) {
    return <AiThinking compact lines={3} steps={[t("memory.loading")]} />;
  }
  if (!memory.thread.length) {
    return (
      <section className="memory">
        <MemoryHead />
        <p className="brief-empty">{t("memory.firstTime")}</p>
      </section>
    );
  }

  return (
    <section className="memory">
      <MemoryHead />
      <ol className="memory-thread" aria-label={t("memory.thread")}>
        {memory.thread.map((item) => (
          <li key={item.session_id}>
            <button type="button" className="memory-chip" onClick={() => onOpenSession?.(item.session_id)} disabled={!onOpenSession}>
              <time>{formatDate(item.started_at)}</time>
              <span>{item.title}</span>
              {!item.has_summary ? <small>{t("memory.noMinutesShort")}</small> : null}
            </button>
          </li>
        ))}
      </ol>

      {error ? <p className="banner">{error}</p> : null}

      {comparing ? (
        <AiThinking compact lines={4} steps={[t("memory.comparing"), t("ai.crossMeetings")]} />
      ) : memory.mode === "before" ? (
        <>
          <Block title={t("memory.lastDecisions")} items={memory.watch} tone="decision" />
          <Block title={t("memory.stillOpen")} items={memory.still_open} tone="open" />
          {!memory.watch.length && !memory.still_open.length ? <p className="brief-empty">{t("memory.nothingBefore")}</p> : null}
          <p className="memory-foot">{t("memory.noMinutes")}</p>
        </>
      ) : !memory.generated ? (
        <div className="memory-cta">
          <p className="brief-empty">{aiReady ? t("memory.readyToCompare") : t("memory.engineOff")}</p>
          <Button size="sm" variant="primary" disabled={!aiReady} onClick={() => void compare()}>
            {t("memory.compare")}
          </Button>
        </div>
      ) : (
        <>
          {memory.stale ? (
            <p className="memory-stale">
              <Icon name="refresh" size={13} />
              {t("memory.stale")}
              <button type="button" className="brief-link" onClick={() => void compare(true)}>
                {t("memory.recompare")}
              </button>
            </p>
          ) : null}
          {memory.resolved.length ? (
            <section className="brief-block">
              <h4>
                {t("memory.resolved")}
                <span className="tab-count">{memory.resolved.length}</span>
              </h4>
              <ul className="memory-list tone-resolved">
                {memory.resolved.map((item, i) => {
                  const checked = item.task_id ? done[item.task_id] : false;
                  return (
                    <li key={`${item.item}-${i}`} className={checked ? "is-done" : ""}>
                      <span className="memory-mark" aria-hidden>
                        <Icon name="check" size={11} />
                      </span>
                      <div>
                        <strong>{item.item}</strong>
                        {item.how ? <p>{item.how}</p> : null}
                        {item.task_id ? (
                          <button type="button" className="memory-task" disabled={checked} onClick={() => void markDone(item.task_id!)}>
                            <Icon name="tasks" size={12} />
                            {checked ? t("memory.taskDone") : t("memory.markTaskDone")}
                          </button>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}
          <Block title={t("memory.stillOpen")} items={memory.still_open} tone="open" />
          {memory.changed.length ? (
            <section className="brief-block">
              <h4>{t("memory.changed")}</h4>
              <ul className="memory-list tone-changed">
                {memory.changed.map((item, i) => (
                  <li key={`${item.before}-${i}`}>
                    <span className="memory-mark" aria-hidden>
                      <Icon name="arrow" size={11} />
                    </span>
                    <div>
                      <s>{item.before}</s>
                      <strong>{item.now}</strong>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          <Block title={t("memory.newItems")} items={memory.new_items} tone="new" />
          <Block title={t("memory.watch")} items={memory.watch} tone="watch" />
          {!memory.resolved.length && !memory.still_open.length && !memory.changed.length && !memory.new_items.length ? (
            <p className="brief-empty">{t("memory.nothingChanged")}</p>
          ) : null}
          {memory.created_at ? (
            <p className="memory-foot">
              {t("memory.generatedAt", { when: formatDate(memory.created_at) })}
              {!memory.stale ? (
                <button type="button" className="brief-link" onClick={() => void compare(true)}>
                  {t("memory.recompare")}
                </button>
              ) : null}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function MemoryHead() {
  const t = useT();
  return (
    <header className="memory-head">
      <Icon name="memory" size={15} />
      <h3 className="with-tip">
        {t("memory.title")}
        <InfoTip text={t("memory.hint")} />
      </h3>
    </header>
  );
}

function Block({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items.length) return null;
  return (
    <section className="brief-block">
      <h4>
        {title}
        <span className="tab-count">{items.length}</span>
      </h4>
      <ul className={`memory-list tone-${tone}`}>
        {items.map((item, i) => (
          <li key={`${item}-${i}`}>
            <span className="memory-mark" aria-hidden />
            <div>{item}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
