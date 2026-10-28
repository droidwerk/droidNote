import { useCallback, useEffect, useState } from "react";

import { api } from "../../shared/api/client";
import type { CalendarEvent, Upcoming } from "../../shared/api/types";
import { useI18n } from "../../shared/i18n";
import { bcp47 } from "../../shared/i18n/locales";
import { Icon } from "../../shared/ui/Icon";
import { BriefCard } from "./BriefCard";

const REFRESH_MS = 5 * 60_000;

interface UpcomingPanelProps {
  disabled?: boolean;
  onRecord: (event: CalendarEvent) => void;
  onOpenSession: (sessionId: string) => void;
  onConnect: () => void;
  onTasksChanged?: () => void;
}

/** Próximas reuniões do calendário (ICS), cada uma com o briefing do que veio antes. */
export function UpcomingPanel({ disabled, onRecord, onOpenSession, onConnect, onTasksChanged }: UpcomingPanelProps) {
  const { t, locale } = useI18n();
  const [data, setData] = useState<Upcoming | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api.upcoming(36);
      setData(next);
      setOpen((current) => current ?? firstSoon(next.events));
    } catch {
      setData(null);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  if (!data) return null;

  if (!data.configured) {
    return (
      <button type="button" className="upcoming-connect" onClick={onConnect}>
        <Icon name="calendar" size={16} />
        <span>
          <strong>{t("calendar.connectTitle")}</strong>
          <small>{t("calendar.connectHint")}</small>
        </span>
        <Icon name="arrow" size={14} />
      </button>
    );
  }

  const tag = bcp47(locale);
  const time = (iso: string) => new Date(iso).toLocaleTimeString(tag, { hour: "2-digit", minute: "2-digit" });
  const day = (iso: string) => {
    const date = new Date(iso);
    const today = new Date();
    if (date.toDateString() === today.toDateString()) return t("calendar.today");
    const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
    if (date.toDateString() === tomorrow.toDateString()) return t("calendar.tomorrow");
    return date.toLocaleDateString(tag, { weekday: "short", day: "2-digit", month: "short" });
  };

  return (
    <section className="upcoming panel">
      <div className="panel-head">
        <div className="panel-title">
          <span className="eyebrow">
            <Icon name="calendar" size={13} />
          </span>
          <h2>{t("calendar.title")}</h2>
          {data.events.length ? <span className="panel-meta">{t("calendar.next36")}</span> : null}
        </div>
        <button type="button" className="tool-btn" onClick={() => void load()} title={t("calendar.refresh")}>
          <Icon name="refresh" size={14} />
        </button>
      </div>
      {data.error ? <p className="upcoming-note">{t("calendar.error", { reason: t(`calendar.err_${errorKey(data.error)}`) })}</p> : null}
      {!data.error && !data.events.length ? <p className="upcoming-note">{t("calendar.empty")}</p> : null}
      <ol className="upcoming-list">
        {data.events.map((event) => {
          const key = `${event.uid}-${event.start}`;
          const expanded = open === key;
          const now = Date.now();
          const live = Date.parse(event.start) <= now && Date.parse(event.end) > now;
          const related = event.brief.related.length;
          return (
            <li key={key} className={expanded ? "upcoming-item is-open" : "upcoming-item"}>
              <div className="upcoming-row">
                <button
                  type="button"
                  className="upcoming-main"
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : key)}
                >
                  <span className="upcoming-when">
                    <small>{live ? t("calendar.now") : day(event.start)}</small>
                    <strong>{time(event.start)}</strong>
                  </span>
                  <span className="upcoming-copy">
                    <strong>{event.title || t("calendar.untitled")}</strong>
                    <small>
                      {event.attendees.length ? t("calendar.people", { count: event.attendees.length }) : t("calendar.noPeople")}
                      {related ? ` · ${t("calendar.related", { count: related })}` : ""}
                      {event.brief.pending.length ? ` · ${t("calendar.pendingCount", { count: event.brief.pending.length })}` : ""}
                    </small>
                  </span>
                </button>
                <button
                  type="button"
                  className="button button-ghost button-sm"
                  disabled={disabled}
                  onClick={() => onRecord(event)}
                >
                  <span className="dot" />
                  {t("calendar.record")}
                </button>
              </div>
              {expanded ? (
                <div className="upcoming-brief">
                  <BriefCard brief={event.brief} compact onOpenSession={onOpenSession} onTasksChanged={onTasksChanged} />
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function firstSoon(events: CalendarEvent[]): string | null {
  const soon = events.find((event) => Date.parse(event.start) - Date.now() < 2 * 3600_000 && event.brief.related.length);
  return soon ? `${soon.uid}-${soon.start}` : null;
}

function errorKey(error: string): string {
  if (error.startsWith("http_")) return "http";
  return ["unreachable", "not_ics", "too_large", "invalid_url"].includes(error) ? error : "unreachable";
}
