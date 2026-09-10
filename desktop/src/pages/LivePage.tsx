import { useEffect, useState, type SyntheticEvent } from "react";

import { api } from "../shared/api/client";
import type { CaptureMode, CaptureState, ChatFocus, Device, MonitorFrame, Person, Provider, Segment, SessionDetail, Summary } from "../shared/api/types";
import { CaptureLanguageMenu } from "../features/capture/CaptureLanguageMenu";
import { CaptureMeter } from "../features/capture/CaptureMeter";
import { TranscriptList } from "../features/transcript/TranscriptList";
import { SummaryPanel } from "../features/summary/SummaryPanel";
import { isCaptureLanguage, useT, type CaptureLanguage } from "../shared/i18n";
import type { TranslateFn } from "../shared/i18n/I18nProvider";
import { Button, Card, PageHeader } from "../shared/ui/primitives";
import { SessionTitle } from "../shared/ui/SessionTitle";
import { mergeSessionSegments } from "../shared/lib/segments";

interface LivePageProps {
  capture: CaptureState;
  sessionId: string | null;
  liveSegments: Segment[];
  busy: boolean;
  pending: "start" | "stop" | null;
  error: string | null;
  micOnly: boolean;
  monitor: MonitorFrame | null;
  asrBusy: boolean;
  asrQueued: number;
  speakersBusy: boolean;
  socketLive: boolean;
  monitorStale: boolean;
  loopbackId: string;
  devices: Device[];
  onMicOnlyChange: (value: boolean) => void;
  onLoopbackChange: (value: string) => void;
  onToggle: () => void;
  onTitleChange: (title: string) => Promise<void>;
  participantIds: string[];
  onParticipantIdsChange: (ids: string[]) => void;
  languageLocked: boolean;
  captureLanguage: CaptureLanguage;
  captureMode: CaptureMode;
  engineProvider?: Provider;
  onCaptureModeChange: (mode: CaptureMode) => void;
  onCaptureLanguageChange: (id: CaptureLanguage) => void;
  onAsk?: (focus: ChatFocus) => void;
}

export function LivePage({
  capture,
  sessionId,
  liveSegments,
  busy,
  pending,
  error,
  micOnly,
  monitor,
  asrBusy,
  asrQueued,
  speakersBusy,
  socketLive,
  monitorStale,
  loopbackId,
  devices,
  onMicOnlyChange,
  onLoopbackChange,
  onToggle,
  onTitleChange,
  participantIds,
  onParticipantIdsChange,
  languageLocked,
  captureLanguage,
  captureMode,
  engineProvider,
  onCaptureModeChange,
  onCaptureLanguageChange,
  onAsk,
}: LivePageProps) {
  const t = useT();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [query, setQuery] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(capture.warning);
  const [people, setPeople] = useState<Person[]>([]);
  const [newName, setNewName] = useState("");
  const [segmentPatches, setSegmentPatches] = useState<Record<string, Segment>>({});
  const [selfPersonId, setSelfPersonId] = useState("");
  const [engineLabel, setEngineLabel] = useState(() => t("engine.defaultEngine"));
  const [setupOpen, setSetupOpen] = useState(false);
  const elapsedMs = useElapsed(capture.started_at ?? null, capture.recording);

  const handleSetupToggle = (event: SyntheticEvent<HTMLDetailsElement>) => {
    setSetupOpen(event.currentTarget.open);
  };

  useEffect(() => {
    if (capture.recording) setSetupOpen(false);
  }, [capture.recording]);

  useEffect(() => {
    setWarning(capture.warning);
  }, [capture.warning]);

  useEffect(() => {
    void api.people().then(setPeople);
    void api.getSettings().then((item) => {
      setSelfPersonId(item.self_person_id ?? "");
      setEngineLabel(
        item.provider === "openai"
          ? t("engine.openaiLabel", { model: item.llm_cloud_model ?? "gpt-4o-mini" })
          : t("engine.localLabel", { model: item.ollama_model }),
      );
    });
  }, [engineProvider, t]);

  useEffect(() => {
    if (!sessionId) {
      setDetail(null);
      setSummary(null);
      return;
    }
    void api.session(sessionId).then((item) => {
      setDetail(item);
      setSummary(item.summary);
      if (item.participants?.length) {
        onParticipantIdsChange(item.participants.map((person) => person.id));
      }
    });
  }, [sessionId, onParticipantIdsChange]);

  const segments = mergeSessionSegments(detail?.segments ?? [], liveSegments, sessionId).map(
    (item) => segmentPatches[item.id] ?? item,
  );
  const filtered = query.trim()
    ? segments.filter((item) => item.text.toLowerCase().includes(query.trim().toLowerCase()))
    : segments;

  const persistParticipants = async (ids: string[]) => {
    onParticipantIdsChange(ids);
    if (sessionId && capture.recording) {
      await api.setParticipants(sessionId, ids);
    }
  };

  const toggleParticipant = async (id: string) => {
    const next = participantIds.includes(id)
      ? participantIds.filter((item) => item !== id)
      : [...participantIds, id];
    await persistParticipants(next);
  };

  const addLivePerson = async () => {
    const cleaned = newName.trim();
    if (!cleaned) return;
    const person = await api.createPerson(cleaned);
    setPeople((current) => (current.some((item) => item.id === person.id) ? current : [...current, person]));
    setNewName("");
    await persistParticipants([...participantIds, person.id]);
  };

  const generate = async () => {
    if (!sessionId) return;
    setLoadingSummary(true);
    setSummaryError(null);
    try {
      setSummary(await api.summarize(sessionId));
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : t("live.noteFail"));
    } finally {
      setLoadingSummary(false);
    }
  };

  const actionLabel =
    pending === "start"
      ? t("live.starting")
      : pending === "stop"
        ? t("live.stopping")
        : capture.recording
          ? t("live.stop")
          : t("live.start");

  const sessionTitle = detail?.session.title ?? t("live.title");

  return (
    <div className="container live">
      <PageHeader
        title={
          sessionId && detail ? (
            <SessionTitle
              value={detail.session.title}
              onCommit={async (title) => {
                await onTitleChange(title);
                setDetail({ ...detail, session: { ...detail.session, title } });
              }}
            />
          ) : (
            <h1>{t("live.title")}</h1>
          )
        }
        description={
          capture.recording
            ? t("live.recording")
            : t("live.idle")
        }
        actions={
          <>
            <CaptureLanguageMenu
              value={isCaptureLanguage(captureLanguage) ? captureLanguage : "pt"}
              disabled={capture.recording || busy}
              onChange={onCaptureLanguageChange}
            />
            <Button
              variant="record"
              recording={capture.recording}
              disabled={busy}
              onClick={onToggle}
            >
              {actionLabel}
            </Button>
          </>
        }
      />
      {error ? <p className="banner">{error}</p> : null}
      {warning ? <p className="warning">{warning}</p> : null}
      {summaryError ? <p className="banner">{summaryError}</p> : null}
      {speakersBusy ? <p className="muted">{t("live.identifying")}</p> : null}

      <div className="capture-modes" role="radiogroup" aria-label={t("live.captureType")}>
        {MODE_CARDS(t).map((item) => (
          <button
            key={item.id}
            type="button"
            role="radio"
            aria-checked={captureMode === item.id}
            className={captureMode === item.id ? "capture-mode is-selected" : "capture-mode"}
            disabled={capture.recording || busy}
            onClick={() => onCaptureModeChange(item.id)}
          >
            <strong>{item.title}</strong>
            <small className="visually-hidden">{item.blurb}</small>
          </button>
        ))}
      </div>

      <CaptureMeter
        recording={capture.recording}
        phase={capture.phase ?? "idle"}
        elapsedMs={elapsedMs}
        socketLive={socketLive}
        stale={monitorStale}
        monitor={monitor}
        asrBusy={asrBusy}
        asrQueued={asrQueued}
      />

      <details className="setup-drawer" open={setupOpen} onToggle={handleSetupToggle}>
        <summary>
          <span className="setup-summary-title">
            <span>
              <strong>{t("live.audioPeople")}</strong>
              <small>{setupSummary(capture, micOnly, participantIds.length, t)}</small>
            </span>
          </span>
          <span className="setup-summary-action">{setupOpen ? t("live.collapse") : t("live.configure")}</span>
        </summary>
        <div className="setup-drawer-body">
          <div className="setup-field">
            <label htmlFor="system-audio">{t("live.systemAudio")}</label>
            <select
              id="system-audio"
              className="select"
              value={loopbackId}
              disabled={capture.recording || busy || micOnly}
              onChange={(event) => onLoopbackChange(event.target.value)}
            >
              <option value="">{t("live.systemAuto")}</option>
              {devices
                .filter((item) => item.kind === "loopback")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.recommended ? t("live.recommendedPrefix") : ""}
                    {item.name}
                  </option>
                ))}
            </select>
            <label className="check-control">
              <input
                type="checkbox"
                checked={micOnly}
                onChange={(event) => onMicOnlyChange(event.target.checked)}
                disabled={capture.recording || busy}
              />
              <span className="check-box" aria-hidden />
              <span>
                <strong>{t("live.micOnlyTitle")}</strong>
                <small>{t("live.micOnlyHint")}</small>
              </span>
            </label>
          </div>
          <div className="setup-field">
            <label htmlFor="self-person">{t("live.youOnMic")}</label>
            <select
              id="self-person"
              className="select"
              value={selfPersonId}
              onChange={(event) => {
                const next = event.target.value;
                setSelfPersonId(next);
                void api.saveSettings({ self_person_id: next });
              }}
            >
              <option value="">{t("settings.notSet")}</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
            <p className="field-help">{t("live.othersUntilNamed")}</p>
          </div>
          <div className="setup-drawer-people">
            <span className="field-label">{t("live.inRoom")}</span>
            <p className="field-help">{t("live.selectWho")}</p>
            <div className="people-chips">
              {people.map((person) => {
                const selected = participantIds.includes(person.id);
                return (
                  <button
                    key={person.id}
                    type="button"
                    className={selected ? "participant-chip is-selected" : "participant-chip"}
                    aria-pressed={selected}
                    onClick={() => void toggleParticipant(person.id)}
                  >
                    <span className="participant-check" aria-hidden>{selected ? "✓" : "+"}</span>
                    <span>{person.name}</span>
                  </button>
                );
              })}
              <input
                className="chip-input"
                placeholder={t("live.namePlaceholder")}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void addLivePerson();
                  }
                }}
              />
            </div>
          </div>
        </div>
      </details>

      <div className={sessionId ? "workspace-grid" : "workspace-grid is-transcript-only"}>
        <Card className="transcript-card">
          <div className="workspace-head">
            <div>
              <h2>{t("live.transcript")}</h2>
            </div>
            <div className="search-wrap">
              <span aria-hidden>
                <svg className="search-glyph" viewBox="0 0 16 16" fill="none">
                  <circle cx="7" cy="7" r="4.25" />
                  <path d="M10.5 10.5 13.25 13.25" />
                </svg>
              </span>
              <input
                className="search"
                aria-label={t("live.searchAria")}
                placeholder={t("live.search")}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          </div>
          <TranscriptList
            segments={filtered}
            query={query}
            emptyHint={emptyHint(capture.recording, asrBusy, t)}
            people={people}
            languageLocked={languageLocked}
            sessionId={sessionId}
            receiving={capture.recording}
            liveLabel={
              asrBusy ? t("live.transcribing") : capture.recording ? t("live.listening") : undefined
            }
            onAskSelected={
              onAsk && sessionId
                ? (segment) =>
                    onAsk({
                      sessionId,
                      sessionTitle: sessionTitle,
                      segmentId: segment.id,
                      excerpt: segment.text,
                    })
                : undefined
            }
            onPatchSegment={async (segmentId, payload) => {
              if (!sessionId) return;
              const updated = await api.assignSegmentSpeaker(sessionId, segmentId, payload);
              const speakerChanged = payload.speaker_id !== undefined || Boolean(payload.name);
              if (speakerChanged) {
                const next = await api.session(sessionId);
                setDetail(next);
                setSegmentPatches({});
                if (payload.name) setPeople(await api.people());
              } else {
                setSegmentPatches((current) => ({ ...current, [updated.id]: updated }));
              }
              if (updated.speaker_id && !participantIds.includes(updated.speaker_id)) {
                await persistParticipants([...participantIds, updated.speaker_id]);
              }
            }}
          />
        </Card>
        {sessionId ? (
          <SummaryPanel
            summary={summary}
            loading={loadingSummary}
            disabled={false}
            title={sessionTitle}
            engineLabel={engineLabel}
            captureMode={detail?.session.capture_mode ?? captureMode}
            onGenerate={() => void generate()}
            onSaveNote={async (markdown) => {
              const next = await api.saveNote(sessionId, markdown);
              setSummary(next);
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function MODE_CARDS(t: TranslateFn): { id: CaptureMode; title: string; blurb: string }[] {
  return [
    {
      id: "dictation",
      title: t("live.dictation"),
      blurb: t("live.dictationBlurb"),
    },
    {
      id: "lecture",
      title: t("live.lecture"),
      blurb: t("live.lectureBlurb"),
    },
    {
      id: "meeting",
      title: t("live.meeting"),
      blurb: t("live.meetingBlurb"),
    },
  ];
}

function setupSummary(
  capture: CaptureState,
  micOnly: boolean,
  participants: number,
  t: TranslateFn,
): string {
  const source = micOnly
    ? t("live.sourceMicOnly")
    : capture.loopback_name
      ? t("live.sourceMicNamed", { name: capture.loopback_name })
      : t("live.sourceMicSystem");
  const people =
    participants === 1
      ? t("live.participantOne")
      : t("live.participantMany", { count: participants });
  return `${source} · ${people}`;
}

function emptyHint(recording: boolean, asrBusy: boolean, t: TranslateFn): string {
  if (!recording) return t("live.emptyIdle");
  if (asrBusy) return t("live.emptyBusy");
  return t("live.emptyListening");
}

function useElapsed(startedAt: string | null, active: boolean): number {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    if (!active || !startedAt) {
      setMs(0);
      return undefined;
    }
    const origin = Date.parse(startedAt);
    if (!Number.isFinite(origin)) {
      setMs(0);
      return undefined;
    }
    const tick = () => setMs(Math.max(0, Date.now() - origin));
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [active, startedAt]);
  return ms;
}
