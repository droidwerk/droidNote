import { useState } from "react";

import { api } from "../../shared/api/client";
import type { Brief, TaskItem } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { formatDate } from "../../shared/lib/format";
import { Icon } from "../../shared/ui/Icon";

interface BriefCardProps {
  brief: Brief;
  compact?: boolean;
  onOpenSession?: (sessionId: string) => void;
  onTasksChanged?: () => void;
}

/** O que ficou da última vez: pendências abertas e decisões das reuniões parecidas. */
export function BriefCard({ brief, compact = false, onOpenSession, onTasksChanged }: BriefCardProps) {
  const t = useT();
  const [done, setDone] = useState<Record<string, boolean>>({});

  const latest = brief.related[0];
  if (!latest) {
    return <p className="brief-empty">{t("brief.firstTime")}</p>;
  }

  const toggle = async (task: TaskItem) => {
    const next = !(done[task.id] ?? task.done);
    setDone((current) => ({ ...current, [task.id]: next }));
    try {
      await api.updateTask(task.id, { done: next });
      onTasksChanged?.();
    } catch {
      setDone((current) => ({ ...current, [task.id]: !next }));
    }
  };

  const earlier = compact ? [] : brief.related.slice(1);

  return (
    <div className={compact ? "brief is-compact" : "brief"}>
      {brief.pending.length ? (
        <section className="brief-block">
          <h4>
            {t("brief.pending")}
            <span className="tab-count">{brief.pending.length}</span>
          </h4>
          <ul className="brief-tasks">
            {brief.pending.slice(0, compact ? 4 : 12).map((task) => {
              const checked = done[task.id] ?? task.done;
              return (
                <li key={task.id} className={checked ? "is-done" : ""}>
                  <button
                    type="button"
                    className="task-check"
                    role="checkbox"
                    aria-checked={checked}
                    aria-label={checked ? t("tasks.reopen") : t("tasks.markDone")}
                    onClick={() => void toggle(task)}
                  >
                    {checked ? <Icon name="check" size={12} /> : null}
                  </button>
                  <span>{task.text}</span>
                  {task.owner ? <small className="task-owner">{task.owner}</small> : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : (
        <p className="brief-empty">{t("brief.nothingPending")}</p>
      )}

      <section className="brief-block">
        <h4>{t("brief.lastTime")}</h4>
        <BriefMeeting item={latest} onOpenSession={onOpenSession} />
      </section>

      {earlier.length ? (
        <section className="brief-block">
          <h4>{t("brief.before")}</h4>
          {earlier.map((item) => (
            <BriefMeeting key={item.session_id} item={item} onOpenSession={onOpenSession} brief />
          ))}
        </section>
      ) : null}
    </div>
  );
}

function BriefMeeting({
  item,
  onOpenSession,
  brief = false,
}: {
  item: Brief["related"][number];
  onOpenSession?: (sessionId: string) => void;
  brief?: boolean;
}) {
  const t = useT();
  return (
    <article className="brief-meeting">
      <header>
        {onOpenSession ? (
          <button type="button" className="brief-link" onClick={() => onOpenSession(item.session_id)}>
            {item.title}
            <Icon name="arrow" size={12} />
          </button>
        ) : (
          <strong>{item.title}</strong>
        )}
        <time>{formatDate(item.started_at)}</time>
        <span className="brief-reason">{t(`brief.reason_${item.reason}`)}</span>
      </header>
      {!brief && item.overview ? <p className="brief-overview">{item.overview}</p> : null}
      {item.decisions.length ? (
        <ul className="brief-decisions">
          {item.decisions.slice(0, brief ? 2 : 5).map((decision) => (
            <li key={decision}>{decision}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
