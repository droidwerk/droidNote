import { useEffect, useState } from "react";

import { api } from "../../shared/api/client";
import type { Settings } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { copyToClipboard } from "../../shared/lib/format";
import { InfoTip } from "../../shared/ui/InfoTip";
import { useConfirm } from "../../shared/ui/ConfirmDialog";
import { Button, Card } from "../../shared/ui/primitives";
import { useToast } from "../../shared/ui/Toast";
import { consentText } from "../consent/consent";

type Persist = (payload: Partial<Settings> & { calendar_ics_url?: string }) => Promise<Settings>;

/** Calendário por URL ICS: só leitura, sem login. A URL fica cifrada neste PC. */
export function CalendarCard({ settings, persist }: { settings: Settings; persist: Persist }) {
  const t = useT();
  const toast = useToast();
  const [editing, setEditing] = useState(!settings.has_calendar);
  const [url, setUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [limited, setLimited] = useState(false);

  useEffect(() => setEditing(!settings.has_calendar), [settings.has_calendar]);

  // 14 dias, como o teste da agenda; o backend guarda o ICS em cache.
  const [busyOnly, setBusyOnly] = useState(false);
  // Sobe a cada agenda salva: trocar de agenda no mesmo host não muda calendar_hint.
  const [calendarRev, setCalendarRev] = useState(0);
  useEffect(() => {
    if (!settings.has_calendar) return setBusyOnly(false);
    let alive = true;
    api
      .upcoming(336)
      .then((next) => alive && setBusyOnly(Boolean(next.busy_only)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [settings.has_calendar, settings.calendar_hint, calendarRev]);

  const test = async () => {
    setTesting(true);
    setResult(null);
    setLimited(false);
    try {
      const outcome = await api.testCalendar(url.trim());
      setLimited(outcome.ok && Boolean(outcome.limited));
      setResult(
        outcome.ok
          ? t("calendar.testOk", { count: outcome.events })
          : t("calendar.error", { reason: t(`calendar.err_${outcome.error?.startsWith("http_") ? "http" : outcome.error ?? "unreachable"}`) }),
      );
      return outcome.ok;
    } catch {
      setResult(t("calendar.error", { reason: t("calendar.err_unreachable") }));
      return false;
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    if (!(await test())) return;
    try {
      const first = !settings.has_calendar;
      const next = await persist({ calendar_ics_url: url.trim() });
      setUrl("");
      setEditing(false);
      setCalendarRev((rev) => rev + 1);
      toast.push({
        tone: "success",
        title: t("calendar.saved"),
        description: first && next.calendar_auto_record ? t("calendar.savedAutoOn") : undefined,
      });
    } catch (err) {
      setResult(err instanceof Error ? err.message : t("settings.saveFail"));
    }
  };

  return (
    <Card className="settings-card settings-card-wide">
      <h2 className="with-tip">{t("calendar.settingsTitle")}<InfoTip text={t("calendar.settingsHelp")} /></h2>
      {settings.has_calendar && !editing ? (
        <div className="calendar-linked">
          <span className="state-led is-on" aria-hidden />
          <span>{t("calendar.linked", { host: settings.calendar_hint || "ICS" })}</span>
          <Button size="sm" variant="quiet" onClick={() => setEditing(true)}>
            {t("calendar.replace")}
          </Button>
          <Button size="sm" onClick={() => void persist({ calendar_ics_url: "" })}>
            {t("calendar.disconnect")}
          </Button>
        </div>
      ) : null}
      {settings.has_calendar && !editing ? (
        <>
        <label className="check-control">
          <input
            type="checkbox"
            checked={settings.calendar_auto_record !== false}
            aria-labelledby="calendar-auto-title"
            aria-describedby="calendar-auto-hint"
            onChange={(event) => void persist({ calendar_auto_record: event.target.checked }).catch(() => toast.push({ tone: "error", title: t("settings.saveFail") }))}
          />
          <span className="check-box" aria-hidden />
          <span>
            <strong id="calendar-auto-title">{t("meeting.calendarAutoRecord")}</strong>
            <small id="calendar-auto-hint">
              {t("meeting.calendarAutoRecordHint")}
              {settings.provider === "openai" ? ` ${t("meeting.calendarAutoRecordCloud")}` : ""}
            </small>
          </span>
        </label>
        {/* Só para agenda livre/ocupado; quem já ligou continua vendo para poder desligar. */}
        {busyOnly || settings.calendar_record_busy === true ? (
        <label className="check-control is-sub">
          <input
            type="checkbox"
            checked={settings.calendar_record_busy === true}
            // Desligar fica sempre à mão (LGPD: revogar tão fácil quanto dar).
            disabled={settings.calendar_auto_record === false && settings.calendar_record_busy !== true}
            aria-labelledby="calendar-busy-title"
            aria-describedby="calendar-busy-hint"
            onChange={(event) => void persist({ calendar_record_busy: event.target.checked }).catch(() => toast.push({ tone: "error", title: t("settings.saveFail") }))}
          />
          <span className="check-box" aria-hidden />
          <span>
            <strong id="calendar-busy-title">{t("meeting.calendarRecordBusy")}</strong>
            <small id="calendar-busy-hint">{t("meeting.calendarRecordBusyHint")}</small>
          </span>
        </label>
        ) : null}
        </>
      ) : (
        <>
          <input
            className="search"
            type="url"
            value={url}
            placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"
            aria-label={t("calendar.urlLabel")}
            onChange={(event) => setUrl(event.target.value)}
          />
          <details className="calendar-where">
            <summary>{t("calendar.whereTitle")}</summary>
            <ul>
              <li>{t("calendar.whereGoogle")}</li>
              <li>{t("calendar.whereOutlook")}</li>
              <li>{t("calendar.whereApple")}</li>
            </ul>
          </details>
          <div className="row">
            <Button variant="primary" disabled={!url.trim() || testing} onClick={() => void save()}>
              {testing ? t("calendar.testing") : t("calendar.connect")}
            </Button>
            {settings.has_calendar ? <Button onClick={() => setEditing(false)}>{t("common.cancel")}</Button> : null}
          </div>
        </>
      )}
      {result ? <p className="field-help">{result}</p> : null}
      {limited ? (
        <p className="field-help field-warn" role="status">
          {t("calendar.limited")}
        </p>
      ) : null}
    </Card>
  );
}

/** Aviso de gravação pronto para colar no chat da reunião. */
export function ConsentCard({ settings, persist }: { settings: Settings; persist: Persist }) {
  const t = useT();
  const toast = useToast();
  const [draft, setDraft] = useState(settings.consent_message ?? "");

  useEffect(() => setDraft(settings.consent_message ?? ""), [settings.consent_message]);

  return (
    <Card className="settings-card settings-card-wide">
      <h2 className="with-tip">{t("consent.settingsTitle")}<InfoTip text={t("consent.settingsHelp")} /></h2>
      <textarea
        className="input consent-text"
        rows={3}
        value={draft}
        placeholder={consentText("", t, settings.provider === "openai")}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          if (draft.trim() !== (settings.consent_message ?? "")) void persist({ consent_message: draft.trim() });
        }}
      />
      <div className="row">
        <Button
          variant="primary"
          onClick={() => {
            void copyToClipboard(consentText(draft, t, settings.provider === "openai")).then((ok) =>
              toast.push({ tone: ok ? "success" : "error", title: ok ? t("consent.copied") : t("consent.copyFail") }),
            );
          }}
        >
          {t("consent.copy")}
        </Button>
        {draft.trim() ? (
          <Button
            variant="quiet"
            onClick={() => {
              setDraft("");
              void persist({ consent_message: "" });
            }}
          >
            {t("consent.reset")}
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

const DAYS = [0, 7, 14, 30, 60, 90, 180, 365];

/** Retenção: apagar áudio e transcrição de gravações antigas, com prévia antes. */
export function RetentionCard({ settings, persist }: { settings: Settings; persist: Persist }) {
  const t = useT();
  const toast = useToast();
  const confirm = useConfirm();
  const audio = settings.retention_audio_days ?? 0;
  const transcript = settings.retention_transcript_days ?? 0;

  const change = async (nextAudio: number, nextTranscript: number) => {
    const tighter = (nextAudio && (!audio || nextAudio < audio)) || (nextTranscript && (!transcript || nextTranscript < transcript));
    if (tighter) {
      const preview = await api.retentionPreview(nextAudio, nextTranscript);
      if (preview.audio_files || preview.transcripts) {
        const ok = await confirm({
          title: t("retention.confirmTitle"),
          description: t("retention.confirmBody", { audio: preview.audio_files, transcripts: preview.transcripts }),
          confirmLabel: t("retention.confirm"),
          tone: "danger",
        });
        if (!ok) return;
        await persist({ retention_audio_days: nextAudio, retention_transcript_days: nextTranscript });
        const report = await api.runRetention();
        toast.push({ tone: "success", title: t("retention.done", { audio: report.audio_files, transcripts: report.transcripts }) });
        return;
      }
    }
    await persist({ retention_audio_days: nextAudio, retention_transcript_days: nextTranscript });
  };

  const select = (value: number, onChange: (days: number) => void, label: string) => (
    <label className="field">
      <span>{label}</span>
      <select className="select" value={value} onChange={(event) => void onChange(Number(event.target.value))}>
        {DAYS.map((days) => (
          <option key={days} value={days}>
            {days ? t("retention.after", { days }) : t("retention.forever")}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <Card className="settings-card settings-card-wide">
      <h2 className="with-tip">
        {t("retention.title")}
        <InfoTip text={`${t("retention.help")} ${t("retention.keeps")}`} />
      </h2>
      <div className="retention-grid">
        {select(audio, (days) => change(days, transcript), t("retention.audio"))}
        {select(transcript, (days) => change(audio, days), t("retention.transcript"))}
      </div>
    </Card>
  );
}
