import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import type { Session } from "../../shared/api/types";
import { bcp47, useI18n } from "../../shared/i18n";
import { titleHasDate, withoutTrailingDate } from "../../shared/lib/format";
import { Icon } from "../../shared/ui/Icon";

/** Limite do backend para `scope.session_ids`. */
export const MAX_CONTEXT = 20;
const VISIBLE_CHIPS = 4;
const DAY = 86_400_000;

export interface PickedSession {
  sessionId: string;
  title: string;
  date: string;
}

export const pickOf = (session: Session): PickedSession => ({
  sessionId: session.id,
  title: session.title,
  date: session.started_at,
});

/** "12/nov": dia e mês curto, sem ponto. */
function shortDate(iso: string, locale: string): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short" }).formatToParts(new Date(iso));
  const day = parts.find((part) => part.type === "day")?.value ?? "";
  const month = (parts.find((part) => part.type === "month")?.value ?? "").replace(/\.$/, "");
  return `${day}/${month}`;
}

interface ContextBarProps {
  sessions: Session[];
  selected: PickedSession[];
  excerpt?: { title?: string; text: string } | null;
  disabled?: boolean;
  onChange: (next: PickedSession[]) => void;
  onClearExcerpt: () => void;
}

/**
 * Uma regra só: os chips são o que a resposta usa; sem chips, ela usa todas as conversas.
 * O "+ Conversa" abre a busca com seleção múltipla.
 */
export function ContextBar({ sessions, selected, excerpt, disabled = false, onChange, onClearExcerpt }: ContextBarProps) {
  const { locale, t } = useI18n();
  const lang = bcp47(locale);
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const remove = (id: string) => onChange(selected.filter((item) => item.sessionId !== id));
  const what =
    selected.length === 0
      ? t("chat.basedOnAll")
      : selected.length === 1
        ? t("chat.basedOnOne")
        : t("chat.basedOnCount", { count: selected.length });

  return (
    <div data-tour="chat-context" className="chat-context-bar">
      <div className="chat-context-chips">
        {excerpt ? (
          <span className="chat-chip is-excerpt" title={excerpt.text}>
            <span>
              {t("chat.selectedExcerpt")}
              {excerpt.title ? ` · ${excerpt.title}` : ""}
            </span>
            <button type="button" aria-label={t("chat.chipRemove", { title: t("chat.selectedExcerpt") })} onClick={onClearExcerpt}>
              <Icon name="close" size={11} />
            </button>
          </span>
        ) : null}
        {selected.slice(0, VISIBLE_CHIPS).map((item) => (
          <span key={item.sessionId} className="chat-chip" title={item.title}>
            <span>
              {item.title}
              {item.date && !titleHasDate(item.title) ? ` · ${shortDate(item.date, lang)}` : ""}
            </span>
            <button
              type="button"
              disabled={disabled}
              aria-label={t("chat.chipRemove", { title: item.title })}
              onClick={() => remove(item.sessionId)}
            >
              <Icon name="close" size={11} />
            </button>
          </span>
        ))}
        {selected.length > VISIBLE_CHIPS ? (
          <button
            type="button"
            className="chat-chip-more"
            aria-label={t("chat.moreChips", { count: selected.length })}
            onClick={() => setOpen(true)}
          >
            +{selected.length - VISIBLE_CHIPS}
          </button>
        ) : null}
        <div className="chat-pick-wrap" ref={wrap}>
          <button
            ref={trigger}
            type="button"
            className="chat-pick-btn"
            disabled={disabled}
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-label={t("chat.addContextAria")}
            onClick={() => setOpen((value) => !value)}
          >
            <Icon name="plus" size={12} />
            <span>{t("chat.addContext")}</span>
          </button>
          {open ? (
            <SessionPicker
              sessions={sessions}
              selected={selected}
              lang={lang}
              onChange={onChange}
              onClose={() => {
                setOpen(false);
                trigger.current?.focus();
              }}
            />
          ) : null}
        </div>
      </div>
      <p className="chat-context-line">
        <span>
          {t("chat.basedOn")} <strong>{what}</strong>
        </span>
        {selected.length ? (
          <button type="button" disabled={disabled} onClick={() => onChange([])}>
            {t("chat.clearContext")}
          </button>
        ) : null}
      </p>
    </div>
  );
}

function SessionPicker({
  sessions,
  selected,
  lang,
  onChange,
  onClose,
}: {
  sessions: Session[];
  selected: PickedSession[];
  lang: string;
  onChange: (next: PickedSession[]) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [days, setDays] = useState<0 | 7 | 30>(0);
  const [folder, setFolder] = useState("");
  const [active, setActive] = useState(0);
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => search.current?.focus(), []);

  const folders = useMemo(() => {
    const seen = new Map<string, string>();
    sessions.forEach((session) => session.tags?.forEach((tag) => seen.set(tag.id, tag.name)));
    return [...seen].sort((a, b) => a[1].localeCompare(b[1]));
  }, [sessions]);

  const ordered = useMemo(
    () => [...sessions].sort((a, b) => b.started_at.localeCompare(a.started_at)),
    [sessions],
  );
  const filtered = !query.trim() && !days && !folder;
  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const since = days ? Date.now() - days * DAY : 0;
    return ordered.filter((session) => {
      if (since && new Date(session.started_at).getTime() < since) return false;
      if (folder && !session.tags?.some((tag) => tag.id === folder)) return false;
      if (!needle) return true;
      const date = new Date(session.started_at);
      const hay = [
        session.title,
        ...(session.tags?.map((tag) => tag.name) ?? []),
        date.toLocaleDateString(lang),
        date.toLocaleDateString(lang, { day: "numeric", month: "long" }),
        shortDate(session.started_at, lang),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(needle);
    });
  }, [ordered, query, days, folder, lang]);

  useEffect(() => setActive(0), [query, days, folder]);

  const chosen = new Set(selected.map((item) => item.sessionId));
  const full = selected.length >= MAX_CONTEXT;
  const toggle = (session: Session) => {
    if (chosen.has(session.id)) onChange(selected.filter((item) => item.sessionId !== session.id));
    else if (!full) onChange([...selected, pickOf(session)]);
  };
  const unchecked = results.filter((session) => !chosen.has(session.id));
  const room = MAX_CONTEXT - selected.length;

  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((value) => (results.length ? (value + step + results.length) % results.length : 0));
      return;
    }
    const isOption = (event.target as HTMLElement).getAttribute("role") === "listbox";
    if (event.key === "Enter" || (event.key === " " && isOption)) {
      const target = results[active];
      if (!target) return;
      event.preventDefault();
      toggle(target);
    }
  };

  useEffect(() => {
    document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, listId]);

  return (
    <div className="chat-pick-pop" role="dialog" aria-label={t("chat.addContextAria")} onKeyDown={onKey}>
      <input
        ref={search}
        type="search"
        className="chat-pick-search"
        value={query}
        placeholder={t("chat.pickSearch")}
        aria-label={t("chat.pickSearch")}
        aria-controls={listId}
        aria-activedescendant={results.length ? `${listId}-${active}` : undefined}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="chat-pick-filters">
        {([7, 30] as const).map((value) => (
          <button
            key={value}
            type="button"
            className="chip"
            aria-pressed={days === value}
            onClick={() => setDays((current) => (current === value ? 0 : value))}
          >
            {t(`chat.pick${value}`)}
          </button>
        ))}
        {folders.length ? (
          <select className="select chat-pick-folder" value={folder} aria-label={t("chat.pickFolder")} onChange={(event) => setFolder(event.target.value)}>
            <option value="">{t("chat.pickAnyFolder")}</option>
            {folders.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <p className="chat-pick-hint">{full ? t("chat.pickLimit", { count: MAX_CONTEXT }) : t("chat.contextHint")}</p>
      <div className="chat-pick-head">
        <span>{filtered ? t("chat.pickRecent") : t("chat.pickResults")}</span>
        {!filtered && unchecked.length > 1 && unchecked.length <= room ? (
          <button
            type="button"
            onClick={() => onChange([...selected, ...unchecked.map(pickOf)])}
          >
            {t("chat.pickMarkAll", { count: unchecked.length })}
          </button>
        ) : null}
      </div>
      {results.length ? (
        <ul
          id={listId}
          className="chat-pick-list"
          role="listbox"
          aria-multiselectable="true"
          aria-label={t("chat.addContextAria")}
          tabIndex={0}
          aria-activedescendant={`${listId}-${active}`}
        >
          {results.map((session, index) => {
            const on = chosen.has(session.id);
            return (
              <li
                key={session.id}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={on}
                aria-disabled={!on && full}
                className={index === active ? "is-active" : undefined}
                onMouseEnter={() => setActive(index)}
                onClick={() => toggle(session)}
              >
                <span className={on ? "chat-pick-box is-on" : "chat-pick-box"} aria-hidden>
                  {on ? <Icon name="check" size={11} /> : null}
                </span>
                <span className="chat-pick-title" title={session.title}>
                  {withoutTrailingDate(session.title)}
                </span>
                <small>{shortDate(session.started_at, lang)}</small>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="chat-pick-empty">{t("chat.pickEmpty")}</p>
      )}
      <div className="chat-pick-foot">
        <button type="button" className="button button-primary button-sm" onClick={onClose}>
          {t("chat.pickDone")}
        </button>
      </div>
    </div>
  );
}
