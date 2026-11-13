import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../shared/api/client";
import type { TaskItem } from "../shared/api/types";
import { bcp47, useI18n } from "../shared/i18n";
import { formatDate } from "../shared/lib/format";
import { Icon } from "../shared/ui/Icon";
import { useToast } from "../shared/ui/Toast";
import { TourButton } from "../features/onboarding/Tour";

type Filter = "open" | "done" | "all";

interface TasksPageProps {
  revision?: number;
  onOpenSession: (sessionId: string) => void;
  onChanged?: () => void;
}

interface Group {
  key: string;
  sessionId: string | null;
  title: string;
  startedAt: string | null;
  items: TaskItem[];
}

/** Central de tarefas: as ações de todas as atas, com dono, prazo e "feito". */
export function TasksPage({ revision = 0, onOpenSession, onChanged }: TasksPageProps) {
  const { locale, t } = useI18n();
  const lang = bcp47(locale);
  const toast = useToast();
  const [items, setItems] = useState<TaskItem[]>([]);
  const [filter, setFilter] = useState<Filter>("open");
  const [owner, setOwner] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [draftOwner, setDraftOwner] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api.tasks("all"));
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, revision]);

  const counts = useMemo(
    () => ({ open: items.filter((item) => !item.done).length, done: items.filter((item) => item.done).length }),
    [items],
  );
  // "Giovanna" sozinha, quando só existe uma "Giovanna Biasin", é a mesma pessoa.
  const canon = useMemo(() => {
    const names = [...new Set(items.flatMap((item) => splitOwners(item.owner)))];
    const map = new Map<string, string>();
    for (const name of names) {
      const fuller = names.filter((other) => other.startsWith(`${name} `));
      map.set(name, !name.includes(" ") && fuller.length === 1 ? fuller[0]! : name);
    }
    return (owner: string | null) => [...new Set(splitOwners(owner).map((name) => map.get(name) ?? name))];
  }, [items]);
  const owners = useMemo(
    () => [...new Set(items.filter((item) => !item.done).flatMap((item) => canon(item.owner)))].sort((a, b) => a.localeCompare(b)),
    [items, canon],
  );

  const visible = items.filter((item) => {
    if (filter === "open" && item.done) return false;
    if (filter === "done" && !item.done) return false;
    if (owner && !canon(item.owner).includes(owner)) return false;
    const needle = query.trim().toLowerCase();
    if (needle && !`${item.text} ${item.owner ?? ""} ${item.session_title ?? ""}`.toLowerCase().includes(needle)) return false;
    return true;
  });
  const groups = groupBySession(visible, t("tasks.loose"));

  const patch = async (task: TaskItem, payload: Partial<Pick<TaskItem, "text" | "owner" | "due" | "done">>) => {
    const previous = items;
    setItems((current) => current.map((item) => (item.id === task.id ? { ...item, ...payload } : item)));
    try {
      const updated = await api.updateTask(task.id, payload);
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      onChanged?.();
    } catch {
      setItems(previous);
      toast.push({ tone: "error", title: t("settings.saveFail") });
    }
  };

  const add = async () => {
    const text = draft.trim();
    if (!text) return;
    try {
      const created = await api.createTask({ text, owner: draftOwner.trim() || null });
      setItems((current) => [created, ...current]);
      setDraft("");
      onChanged?.();
    } catch {
      toast.push({ tone: "error", title: t("settings.saveFail") });
    }
  };

  const startEdit = (task: TaskItem) => {
    setEditing(task.id);
    setEditDraft(task.text);
  };

  const remove = async (task: TaskItem) => {
    setItems((current) => current.filter((item) => item.id !== task.id));
    try {
      await api.deleteTask(task.id);
      onChanged?.();
    } catch {
      void load();
    }
  };

  return (
    <div className="page tasks-page">
      <header className="page-head">
        <div className="page-head-copy">
          <h1>{t("tasks.title")}</h1>
          <p className="muted">{t("tasks.summary", { open: counts.open, done: counts.done })}</p>
        </div>
        <div className="page-actions">
          <TourButton chapter="tarefas" />
        </div>
      </header>

      <form
        data-tour="task-new"
        className="task-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void add();
        }}
      >
        <Icon name="plus" size={16} />
        <input
          className="task-composer-text"
          value={draft}
          placeholder={t("tasks.newPlaceholder")}
          aria-label={t("tasks.newPlaceholder")}
          onChange={(event) => setDraft(event.target.value)}
        />
        <input
          className="task-composer-owner"
          value={draftOwner}
          placeholder={t("tasks.ownerPlaceholder")}
          aria-label={t("tasks.ownerPlaceholder")}
          onChange={(event) => setDraftOwner(event.target.value)}
        />
        <button type="submit" className="tool-btn" disabled={!draft.trim()}>
          {t("tasks.add")}
        </button>
      </form>

      <div data-tour="task-filters" className="task-filters">
        <div className="segmented" role="radiogroup" aria-label={t("tasks.filterAria")}>
          {(["open", "done", "all"] as const).map((id) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={filter === id}
              className={filter === id ? "on" : ""}
              onClick={() => setFilter(id)}
            >
              {t(`tasks.filter_${id}`)}
              {id !== "all" ? <span className={id === "done" ? "tab-count is-neutral" : "tab-count"}>{counts[id]}</span> : null}
            </button>
          ))}
        </div>
        {owners.length ? (
          <div className="chips task-owners">
            {owners.map((name) => (
              <button
                key={name}
                type="button"
                className={owner === name ? "chip is-on" : "chip"}
                aria-pressed={owner === name}
                onClick={() => setOwner(owner === name ? null : name)}
              >
                {name}
              </button>
            ))}
          </div>
        ) : null}
        <label className="search-field">
          <Icon name="search" size={15} />
          <input
            aria-label={t("tasks.search")}
            placeholder={t("tasks.search")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      {groups.length === 0 ? (
        <div data-tour="task-list" className="empty-block task-empty">
          <Icon name="tasks" size={22} />
          <strong>{filter === "done" ? t("tasks.emptyDone") : t("tasks.emptyOpen")}</strong>
          <small>{t("tasks.emptyHint")}</small>
        </div>
      ) : (
        <div data-tour="task-list" className="task-groups">
          {groups.map((group) => (
            <section className="task-group" key={group.key}>
              <header className="task-group-head">
                {group.sessionId ? (
                  <button type="button" className="task-group-link" onClick={() => onOpenSession(group.sessionId as string)}>
                    <span>{group.title}</span>
                    <Icon name="arrow" size={13} />
                  </button>
                ) : (
                  <span className="task-group-link is-static">{group.title}</span>
                )}
                {group.startedAt ? <time>{formatDate(group.startedAt)}</time> : null}
              </header>
              <ul className="task-list">
                {group.items.map((task) => (
                  <li key={task.id} className={task.done ? "task-row is-done" : "task-row"}>
                    <button
                      type="button"
                      className="task-check"
                      role="checkbox"
                      aria-checked={task.done}
                      aria-label={task.done ? t("tasks.reopen") : t("tasks.markDone")}
                      onClick={() => void patch(task, { done: !task.done })}
                    >
                      {task.done ? <Icon name="check" size={13} /> : null}
                    </button>
                    {editing === task.id ? (
                      <input
                        className="task-edit"
                        value={editDraft}
                        autoFocus
                        onChange={(event) => setEditDraft(event.target.value)}
                        onBlur={() => {
                          setEditing(null);
                          if (editDraft.trim() && editDraft.trim() !== task.text) void patch(task, { text: editDraft.trim() });
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") event.currentTarget.blur();
                          if (event.key === "Escape") setEditing(null);
                        }}
                      />
                    ) : (
                      <span
                        className="task-text"
                        tabIndex={0}
                        title={t("tasks.editHint")}
                        onDoubleClick={() => startEdit(task)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === "F2") {
                            event.preventDefault();
                            startEdit(task);
                          }
                        }}
                      >
                        {task.text}
                      </span>
                    )}
                    <span className="task-meta">
                      <span className="task-owner-cell">{task.owner ? <span className="task-owner" title={task.owner}>{task.owner}</span> : null}</span>
                      <span className="task-due-cell">
                        {task.due ? (
                          <span className="task-due" title={task.due}>
                            {anchoredDue(task.due, task.session_started_at, lang)}
                          </span>
                        ) : null}
                      </span>
                      <span className="task-origin-cell">
                        {task.origin === "ai" ? (
                          <span className="task-origin" role="img" aria-label={t("tasks.fromNote")} title={t("tasks.fromNote")}>
                            <Icon name="spark" size={12} />
                          </span>
                        ) : null}
                      </span>
                    </span>
                    <button
                      type="button"
                      className="task-remove is-edit"
                      aria-label={t("tasks.edit")}
                      title={t("tasks.edit")}
                      onClick={() => startEdit(task)}
                    >
                      <Icon name="edit" size={14} />
                    </button>
                    <button
                      type="button"
                      className="task-remove"
                      aria-label={t("common.delete")}
                      title={t("common.delete")}
                      onClick={() => void remove(task)}
                    >
                      <Icon name="trash" size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

/** "Bufon e Giovanna" vira duas pessoas no filtro. */
function splitOwners(owner: string | null): string[] {
  if (!owner) return [];
  return owner
    .split(/\s*(?:,|;|&|\/|\s(?:e|and|y|et|und|и)\s)\s*/i)
    .map((name) => name.trim())
    .filter(Boolean);
}

const DUE_WORDS: [number, string[]][] = [
  [2, ["depois de amanhã", "day after tomorrow", "pasado mañana", "après-demain", "dopodomani", "übermorgen", "послезавтра"]],
  [1, ["amanhã", "tomorrow", "mañana", "demain", "domani", "morgen", "завтра"]],
  [0, ["hoje", "today", "hoy", "aujourd'hui", "oggi", "heute", "сегодня"]],
];

/**
 * Prazo relativo ("Amanhã") envelhece: vira "Amanhã · 13/11", contado da data da reunião.
 * Dia da semana ("sexta") conta até a próxima sexta depois da reunião.
 */
function anchoredDue(due: string, startedAt: string | null, lang: string): string {
  if (!startedAt) return due;
  const base = new Date(startedAt);
  if (Number.isNaN(base.getTime())) return due;
  // "Até amanhã" conta como "amanhã".
  const lower = due
    .trim()
    .toLocaleLowerCase(lang)
    .replace(/^(?:até|by|until|hasta|jusqu'à|entro|bis|до)\s+/, "");
  let offset: number | undefined;
  let word = "";
  for (const [days, words] of DUE_WORDS) {
    const hit = words.find((item) => lower.startsWith(item));
    if (hit) {
      offset = days;
      word = hit;
      break;
    }
  }
  if (offset === undefined) {
    for (let day = 0; day < 7; day += 1) {
      // 2023-01-01 foi domingo: day 0 = domingo, como Date.getDay().
      const name = new Date(2023, 0, 1 + day).toLocaleDateString(lang, { weekday: "long" }).toLocaleLowerCase(lang);
      const short = name.split("-")[0]!;
      if (lower.startsWith(name) || lower.startsWith(short)) {
        offset = (day - base.getDay() + 7) % 7 || 7;
        word = lower.startsWith(name) ? name : short;
        break;
      }
    }
  }
  if (offset === undefined) return due;
  const at = new Date(base.getFullYear(), base.getMonth(), base.getDate() + offset);
  // Forma curta "Amanhã · 13/11": a data nunca some; o texto inteiro fica no title.
  const label = word.charAt(0).toLocaleUpperCase(lang) + word.slice(1);
  return `${label} · ${at.toLocaleDateString(lang, { day: "2-digit", month: "2-digit" })}`;
}

function groupBySession(items: TaskItem[], looseTitle: string): Group[] {
  const groups = new Map<string, Group>();
  for (const item of items) {
    const key = item.session_id ?? "__loose";
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        sessionId: item.session_id,
        title: item.session_id ? item.session_title ?? "—" : looseTitle,
        startedAt: item.session_started_at,
        items: [],
      };
      groups.set(key, group);
    }
    group.items.push(item);
  }
  return [...groups.values()].sort((a, b) => {
    if (!a.sessionId) return -1;
    if (!b.sessionId) return 1;
    return (b.startedAt ?? "").localeCompare(a.startedAt ?? "");
  });
}
