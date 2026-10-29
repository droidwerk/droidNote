import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../shared/api/client";
import type {
  Brief,
  CalendarEvent,
  CaptureMode,
  CaptureState,
  ChatFocus,
  Device,
  MonitorFrame,
  NoteTemplate,
  Person,
  Provider,
  Segment,
  SessionDetail,
  Summary,
} from "../shared/api/types";
import { BriefCard } from "../features/brief/BriefCard";
import { MindMapPanel } from "../features/mindmap/MindMapPanel";
import { MemoryPanel } from "../features/memory/MemoryPanel";
import { ContextPanel } from "../features/context/ContextPanel";
import { SideTabButton } from "./SessionPage";
import { UpcomingPanel } from "../features/brief/UpcomingPanel";
import { CaptureDeck } from "../features/capture/CaptureDeck";
import { NoteDocument } from "../features/document/NoteDocument";
import { CaptureLanguageMenu } from "../features/capture/CaptureLanguageMenu";
import { UserNotes } from "../features/notes/UserNotes";
import { TemplatePicker } from "../features/templates/TemplatePicker";
import { SummaryPanel } from "../features/summary/SummaryPanel";
import { DockToggle, TranscriptTicker, useTranscriptDock } from "../features/transcript/TranscriptDock";
import { TranscriptList } from "../features/transcript/TranscriptList";
import { VoiceRoster } from "../features/voices/VoiceRoster";
import { VoiceTimeline } from "../features/voices/VoiceTimeline";
import { isCaptureLanguage, pluralForm, useI18n, type CaptureLanguage } from "../shared/i18n";
import type { TranslateFn } from "../shared/i18n/I18nProvider";
import { mergeSegmentLists } from "../shared/lib/segments";
import { buildRoster, countWords, mergeVoicesByPerson } from "../shared/lib/voices";
import { AiThinking } from "../shared/ui/AiThinking";
import { InfoTip } from "../shared/ui/InfoTip";
import { Icon, type IconName } from "../shared/ui/Icon";
import { SessionTitle } from "../shared/ui/SessionTitle";
import { useToast } from "../shared/ui/Toast";

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
  voicesRevision: number;
  voiceReady: boolean;
  voiceDownloading: boolean;
  onDownloadVoice: () => void;
  onMicOnlyChange: (value: boolean) => void;
  onLoopbackChange: (value: string) => void;
  onToggle: () => void;
  onTitleChange: (title: string) => Promise<void>;
  participantIds: string[];
  onParticipantIdsChange: (ids: string[]) => void;
  languageLocked: boolean;
  captureLanguage: CaptureLanguage;
  captureMode: CaptureMode;
  templates: NoteTemplate[];
  templateId: string | null;
  onTemplateChange: (id: string | null) => void;
  notesRevision: number;
  onOpenMini: () => void;
  onCopyConsent: () => void;
  tasksRevision: number;
  onTasksChanged: () => void;
  onOpenSession: (sessionId: string) => void;
  onConnectCalendar: () => void;
  onRecordEvent: (event: CalendarEvent) => void;
  /** Ata gerada sozinha ao parar: em andamento ("start") ou pronta (muda a revisão). */
  summaryBusySessionId?: string | null;
  summaryRevision?: number;
  memoryRevision?: number;
  onOpenSettings?: () => void;
  engineProvider?: Provider;
  onCaptureModeChange: (mode: CaptureMode) => void;
  onCaptureLanguageChange: (id: CaptureLanguage) => void;
  onAsk?: (focus: ChatFocus) => void;
}

type SideTab = "doc" | "notes" | "context" | "brief" | "mindmap" | "voices";

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
  voicesRevision,
  voiceReady,
  voiceDownloading,
  onDownloadVoice,
  onMicOnlyChange,
  onLoopbackChange,
  onToggle,
  onTitleChange,
  participantIds,
  onParticipantIdsChange,
  languageLocked,
  captureLanguage,
  captureMode,
  templates,
  templateId,
  onTemplateChange,
  notesRevision,
  onOpenMini,
  onCopyConsent,
  tasksRevision,
  onTasksChanged,
  onOpenSession,
  onConnectCalendar,
  onRecordEvent,
  summaryBusySessionId = null,
  summaryRevision = 0,
  memoryRevision = 0,
  onOpenSettings,
  engineProvider,
  onCaptureModeChange,
  onCaptureLanguageChange,
  onAsk,
}: LivePageProps) {
  const { t, locale } = useI18n();
  const toast = useToast();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [query, setQuery] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [segmentPatches, setSegmentPatches] = useState<Record<string, Segment>>({});
  const [selfPersonId, setSelfPersonId] = useState("");
  const [engineLabel, setEngineLabel] = useState(() => t("engine.defaultEngine"));
  const [side, setSide] = useState<SideTab>("doc");
  const [citeMs, setCiteMs] = useState<number | null>(null);
  const [dockMin, toggleDock] = useTranscriptDock();
  const [refining, setRefining] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(null);
  const elapsedMs = useElapsed(capture.started_at ?? null, capture.recording);

  useEffect(() => {
    setSide(capture.recording ? "notes" : "doc");
  }, [capture.recording]);

  // Briefing da sessão: reuniões parecidas (título ou pessoas) e o que ficou pendente.
  useEffect(() => {
    if (!sessionId) {
      setBrief(null);
      return;
    }
    let alive = true;
    void api
      .brief({ sessionId })
      .then((next) => alive && setBrief(next))
      .catch(() => alive && setBrief(null));
    return () => {
      alive = false;
    };
  }, [sessionId, tasksRevision, detail?.session.title, participantIds]);

  const loadPeople = useCallback(async () => {
    try {
      setPeople(await api.people());
    } catch {
      /* lista opcional */
    }
  }, []);

  useEffect(() => {
    void loadPeople();
    void api.getSettings().then((item) => {
      setSelfPersonId(item.self_person_id ?? "");
      setEngineLabel(
        item.provider === "openai"
          ? t("engine.openaiLabel", { model: item.llm_cloud_model ?? "gpt-4o-mini" })
          : t("engine.localLabel", { model: item.ollama_model }),
      );
    });
  }, [engineProvider, t, loadPeople]);

  const reload = useCallback(async () => {
    if (!sessionId) return;
    const item = await api.session(sessionId);
    setDetail(item);
    setSummary(item.summary);
    setSegmentPatches({});
    return item;
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setDetail(null);
      setSummary(null);
      return;
    }
    void reload().then((item) => {
      if (item?.participants?.length) onParticipantIdsChange(item.participants.map((person) => person.id));
    });
  }, [sessionId, reload, onParticipantIdsChange]);

  const lastSummaryRevision = useRef(summaryRevision);
  useEffect(() => {
    if (summaryRevision === lastSummaryRevision.current) return;
    lastSummaryRevision.current = summaryRevision;
    void reload();
  }, [summaryRevision, reload]);

  const cite = (ms: number) => {
    if (dockMin) toggleDock();
    setCiteMs(ms + Math.random() * 0.5);
  };

  // O motor de voz reagrupou as vozes: rótulos novos na tela.
  const lastRevision = useRef(voicesRevision);
  useEffect(() => {
    if (voicesRevision === lastRevision.current) return;
    lastRevision.current = voicesRevision;
    void reload();
    void loadPeople();
  }, [voicesRevision, reload, loadPeople]);

  const scopedLive = sessionId ? liveSegments.filter((item) => item.session_id === sessionId) : liveSegments;
  const merged = mergeVoicesByPerson(
    mergeSegmentLists(scopedLive, detail?.segments ?? []).map((item) => segmentPatches[item.id] ?? item),
  );
  const segments = merged.segments;
  const filtered = query.trim()
    ? segments.filter((item) => item.text.toLowerCase().includes(query.trim().toLowerCase()))
    : segments;
  const roster = useMemo(() => buildRoster(segments, people), [segments, people]);
  const words = useMemo(() => countWords(segments), [segments]);

  const persistParticipants = async (ids: string[]) => {
    onParticipantIdsChange(ids);
    if (sessionId && capture.recording) await api.setParticipants(sessionId, ids);
  };

  const sessionTemplate = detail?.session.template_id ?? (capture.recording ? templateId : null);

  const generate = async (chosen?: string | null) => {
    if (!sessionId) return;
    setLoadingSummary(true);
    setSummaryError(null);
    try {
      setSummary(await api.summarize(sessionId, chosen === undefined ? sessionTemplate : chosen));
      if (chosen !== undefined && detail) {
        setDetail({ ...detail, session: { ...detail.session, template_id: chosen } });
      }
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : t("live.noteFail"));
    } finally {
      setLoadingSummary(false);
    }
  };

  const assignVoice = async (cluster: string, payload: { person_id?: string | null; name?: string }) => {
    if (!sessionId) return;
    try {
      // Voz exibida pode juntar várias vozes reais da mesma pessoa: o nome vale para todas.
      let result = await api.assignVoice(sessionId, cluster, payload);
      for (const other of (merged.members.get(cluster) ?? [cluster]).filter((item) => item !== cluster)) {
        result = await api.assignVoice(sessionId, other, payload);
      }
      setDetail((current) => (current ? { ...current, segments: result.segments } : current));
      setSegmentPatches({});
      await loadPeople();
    } catch (err) {
      toast.push({ tone: "error", title: err instanceof Error ? err.message : t("settings.saveFail") });
    }
  };

  const refine = async () => {
    if (!sessionId) return;
    setRefining(true);
    try {
      const result = await api.refineVoices(sessionId);
      setDetail((current) => (current ? { ...current, segments: result.segments } : current));
      setSegmentPatches({});
    } finally {
      setRefining(false);
    }
  };

  const sessionTitle = detail?.session.title ?? t("live.title");
  const mode = detail?.session.capture_mode && !capture.recording ? detail.session.capture_mode : captureMode;

  const toolbar = (
    <>
      <div className="mode-switch" role="radiogroup" aria-label={t("live.captureType")}>
        {MODES(t).map((item) => (
          <button
            key={item.id}
            type="button"
            role="radio"
            aria-checked={captureMode === item.id}
            className={captureMode === item.id ? "is-on" : ""}
            disabled={capture.recording || busy}
            title={item.blurb}
            onClick={() => onCaptureModeChange(item.id)}
          >
            <Icon name={item.icon} size={15} />
            {item.title}
          </button>
        ))}
      </div>
      <CaptureLanguageMenu
        value={isCaptureLanguage(captureLanguage) ? captureLanguage : "pt"}
        disabled={capture.recording || busy}
        onChange={onCaptureLanguageChange}
      />
      <TemplatePicker
        compact
        templates={templates}
        value={templateId}
        disabled={capture.recording || busy}
        onChange={onTemplateChange}
      />
      <SourcesMenu
        capture={capture}
        busy={busy}
        micOnly={micOnly}
        loopbackId={loopbackId}
        devices={devices}
        people={people}
        selfPersonId={selfPersonId}
        participantIds={participantIds}
        t={t}
        onLoopbackChange={onLoopbackChange}
        onMicOnlyChange={onMicOnlyChange}
        onSelfChange={(next) => {
          setSelfPersonId(next);
          void api.saveSettings({ self_person_id: next });
        }}
        onParticipants={(ids) => void persistParticipants(ids)}
        onCreatePerson={async (name) => {
          const person = await api.createPerson(name);
          await loadPeople();
          await persistParticipants([...participantIds, person.id]);
        }}
      />
    </>
  );

  return (
    <div className="page console">
      <header className="page-head">
        <div className="page-head-copy">
          {capture.recording || (sessionId && detail) ? (
            <span className="eyebrow">
              {capture.recording ? t("status.live") : t(`live.${mode}`)}
            </span>
          ) : null}
          {sessionId && detail ? (
            <SessionTitle
              value={detail.session.title}
              onCommit={async (title) => {
                await onTitleChange(title);
                setDetail({ ...detail, session: { ...detail.session, title } });
              }}
            />
          ) : (
            <h1>{t("live.title")}</h1>
          )}
        </div>
        <div className="page-actions">
          <button type="button" className="tool-btn is-icon" onClick={onCopyConsent} title={t("consent.copyHint")} aria-label={t("consent.copyHint")}>
            <Icon name="shield" size={15} />
          </button>
          <button type="button" className="tool-btn is-icon" onClick={onOpenMini} title={t("mini.openHint")} aria-label={t("mini.openHint")}>
            <Icon name="chip" size={15} />
          </button>
        </div>
      </header>

      {error ? <p className="banner">{error}</p> : null}
      {capture.warning ? <p className="warning">{capture.warning}</p> : null}
      {summaryError ? <p className="banner">{summaryError}</p> : null}

      <CaptureDeck
        recording={capture.recording}
        pending={pending}
        busy={busy}
        phase={capture.phase ?? "idle"}
        elapsedMs={elapsedMs}
        socketLive={socketLive}
        stale={monitorStale}
        monitor={monitor}
        asrBusy={asrBusy}
        asrQueued={asrQueued}
        micOnly={micOnly || captureMode === "dictation"}
        people={people}
        onToggle={onToggle}
        toolbar={toolbar}
      />

      {!capture.recording ? (
        <UpcomingPanel
          disabled={busy || pending !== null}
          onRecord={onRecordEvent}
          onOpenSession={onOpenSession}
          onConnect={onConnectCalendar}
          onTasksChanged={onTasksChanged}
        />
      ) : null}

      {sessionId || capture.recording ? (
      <div className={sessionId ? `workspace is-ai-first${dockMin ? " is-dock-min" : ""}` : "workspace is-solo"}>
        <section className="panel transcript-panel">
          <div className="panel-head">
            <div className="panel-title">
              <h2>{t("live.transcript")}</h2>
              {segments.length ? (
                <span className="panel-meta">
                  {t(`transcript.${pluralForm(locale, segments.length)}`, { count: segments.length })} ·{" "}
                  {t("console.words", { count: words })}
                </span>
              ) : null}
            </div>
            {sessionId ? <DockToggle min={dockMin} onToggle={toggleDock} /> : null}
            {!dockMin || !sessionId ? (
              <label className="search-field">
                <Icon name="search" size={15} />
                <input
                  aria-label={t("live.searchAria")}
                  placeholder={t("live.search")}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
            ) : null}
          </div>
          {dockMin && sessionId ? (
            <TranscriptTicker segments={segments} people={people} live={capture.recording} onExpand={toggleDock} />
          ) : (
          <TranscriptList
            focusMs={citeMs}
            segments={filtered}
            query={query}
            emptyHint={emptyHint(capture.recording, asrBusy, t)}
            people={people}
            languageLocked={languageLocked}
            sessionId={sessionId}
            receiving={capture.recording}
            liveLabel={asrBusy ? t("live.transcribing") : capture.recording ? t("live.listening") : undefined}
            onAskSelected={
              onAsk && sessionId
                ? (segment) =>
                    onAsk({ sessionId, sessionTitle, segmentId: segment.id, excerpt: segment.text })
                : undefined
            }
            onPatchSegment={async (segmentId, payload) => {
              if (!sessionId) return;
              const updated = await api.assignSegmentSpeaker(sessionId, segmentId, payload);
              const speakerChanged = payload.speaker_id !== undefined || Boolean(payload.name);
              if (speakerChanged) {
                await reload();
                if (payload.name) await loadPeople();
              } else {
                setSegmentPatches((current) => ({ ...current, [updated.id]: updated }));
              }
              if (updated.speaker_id && !participantIds.includes(updated.speaker_id)) {
                await persistParticipants([...participantIds, updated.speaker_id]);
              }
            }}
          />
          )}
          {speakersBusy ? <p className="panel-foot">{t("live.identifying")}</p> : null}
        </section>

        {sessionId ? (
          <aside className="panel side-panel">
            <div className="tabs" role="tablist">
              <SideTabButton id="doc" icon="spark" label={t("doc.tab")} side={side} onPick={setSide} />
              <SideTabButton id="notes" icon="edit" label={t("notes.tab")} side={side} onPick={setSide} />
              <SideTabButton id="context" icon="attach" label={t("context.tab")} side={side} onPick={setSide} />
              <SideTabButton id="mindmap" icon="mindmap" label={t("mindmap.tab")} side={side} onPick={setSide} />
              <SideTabButton id="brief" icon="memory" label={t("memory.tab")} side={side} onPick={setSide} count={brief?.pending.length} />
              <SideTabButton id="voices" icon="voice" label={t("voices.title")} side={side} onPick={setSide} count={roster.length} />
            </div>
            {side === "notes" ? (
              <div className="side-body">
                <UserNotes
                  sessionId={sessionId}
                  recording={capture.recording}
                  revision={notesRevision + summaryRevision}
                  onSeek={cite}
                  onTasksChanged={onTasksChanged}
                  onAsk={onAsk ? (text) => onAsk({ sessionId, sessionTitle, prompt: text }) : undefined}
                />
              </div>
            ) : side === "context" ? (
              <div className="side-body">
                <ContextPanel sessionId={sessionId} revision={summaryRevision} />
              </div>
            ) : side === "doc" ? (
              <div className="side-body">
                <NoteDocument
                  aiFirst={!capture.recording && Boolean(summary)}
                  engineRevision={summaryRevision}
                  onOpenSettings={onOpenSettings}
                  aiNote={
                    <SummaryPanel
                      summary={summary}
                      loading={loadingSummary || summaryBusySessionId === sessionId}
                      disabled={false}
                      title={sessionTitle}
                      engineLabel={engineLabel}
                      captureMode={detail?.session.capture_mode ?? captureMode}
                      templates={templates}
                      templateId={sessionTemplate}
                      onGenerate={(chosen) => void generate(chosen)}
                      onCite={cite}
                      onSaveNote={async (markdown) => {
                        const next = await api.saveNote(sessionId, markdown);
                        setSummary(next);
                      }}
                    />
                  }
                />
              </div>
            ) : side === "mindmap" ? (
              <div className="side-body">
                <MindMapPanel
                  sessionId={sessionId}
                  title={sessionTitle}
                  hasSummary={Boolean(summary)}
                  revision={summaryRevision + tasksRevision}
                  onCite={cite}
                />
              </div>
            ) : side === "brief" ? (
              <div className="side-body">
                <MemoryPanel
                  sessionId={sessionId}
                  revision={summaryRevision + memoryRevision + tasksRevision}
                  aiReady={!capture.recording}
                  onOpenSession={onOpenSession}
                  onTasksChanged={onTasksChanged}
                />
                {brief ? (
                  <BriefCard brief={brief} onOpenSession={onOpenSession} onTasksChanged={onTasksChanged} />
                ) : (
                  <AiThinking compact lines={3} steps={[t("brief.loading"), t("ai.crossMeetings")]} />
                )}
              </div>
            ) : (
              <div className="side-body">
                <VoiceRoster
                  roster={roster}
                  people={people}
                  engineReady={voiceReady}
                  speakingCluster={capture.recording ? monitor?.voice?.cluster ?? null : null}
                  refining={refining}
                  onAssign={assignVoice}
                  onRefine={() => void refine()}
                  onDownloadEngine={onDownloadVoice}
                  engineBusy={voiceDownloading}
                />
                <VoiceTimeline
                  segments={segments}
                  roster={roster}
                  durationMs={capture.recording ? elapsedMs : detail?.session.duration_ms ?? 0}
                />
              </div>
            )}
          </aside>
        ) : null}
      </div>
      ) : null}
    </div>
  );
}

function SourcesMenu({
  capture,
  busy,
  micOnly,
  loopbackId,
  devices,
  people,
  selfPersonId,
  participantIds,
  t,
  onLoopbackChange,
  onMicOnlyChange,
  onSelfChange,
  onParticipants,
  onCreatePerson,
}: {
  capture: CaptureState;
  busy: boolean;
  micOnly: boolean;
  loopbackId: string;
  devices: Device[];
  people: Person[];
  selfPersonId: string;
  participantIds: string[];
  t: TranslateFn;
  onLoopbackChange: (value: string) => void;
  onMicOnlyChange: (value: boolean) => void;
  onSelfChange: (value: string) => void;
  onParticipants: (ids: string[]) => void;
  onCreatePerson: (name: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const summary = micOnly
    ? t("live.sourceMicOnly")
    : capture.loopback_name
      ? t("live.sourceMicNamed", { name: capture.loopback_name })
      : t("live.sourceMicSystem");

  return (
    <div className="sources" ref={ref}>
      <button type="button" className="tool-btn" aria-expanded={open} onClick={() => setOpen((value) => !value)} title={summary}>
        <Icon name={micOnly ? "mic" : "system"} size={15} />
        <span>{t("console.sources")}</span>
        <small>{micOnly ? "1 CH" : "2 CH"}</small>
      </button>
      {open ? (
        <div className="popover sources-pop">
          <p className="popover-title">{summary}</p>
          <label className="field">
            <span>{t("live.systemAudio")}</span>
            <select
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
          </label>
          <label className="check-control">
            <input type="checkbox" checked={micOnly} disabled={capture.recording || busy} onChange={(event) => onMicOnlyChange(event.target.checked)} />
            <span className="check-box" aria-hidden />
            <span>
              <strong className="with-tip">{t("live.micOnlyTitle")}<InfoTip text={t("live.micOnlyHint")} /></strong>
            </span>
          </label>
          <label className="field">
            <span className="with-tip">
              {t("live.youOnMic")}
              <InfoTip text={t("voices.selfHint")} />
            </span>
            <select className="select" value={selfPersonId} onChange={(event) => onSelfChange(event.target.value)}>
              <option value="">{t("settings.notSet")}</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            <span className="with-tip">
              {t("live.inRoom")}
              <InfoTip text={t("live.othersUntilNamed")} />
            </span>
            <div className="chips">
              {people.map((person) => {
                const selected = participantIds.includes(person.id);
                return (
                  <button
                    key={person.id}
                    type="button"
                    className={selected ? "chip is-on" : "chip"}
                    aria-pressed={selected}
                    onClick={() =>
                      onParticipants(selected ? participantIds.filter((id) => id !== person.id) : [...participantIds, person.id])
                    }
                  >
                    {person.name}
                  </button>
                );
              })}
              <input
                className="chip-input"
                placeholder={t("live.namePlaceholder")}
                value={name}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" || !name.trim()) return;
                  event.preventDefault();
                  void onCreatePerson(name.trim()).then(() => setName(""));
                }}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MODES(t: TranslateFn): { id: CaptureMode; title: string; blurb: string; icon: IconName }[] {
  return [
    { id: "dictation", title: t("live.dictation"), blurb: t("live.dictationBlurb"), icon: "dictation" },
    { id: "lecture", title: t("live.lecture"), blurb: t("live.lectureBlurb"), icon: "lecture" },
    { id: "meeting", title: t("live.meeting"), blurb: t("live.meetingBlurb"), icon: "meeting" },
  ];
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
