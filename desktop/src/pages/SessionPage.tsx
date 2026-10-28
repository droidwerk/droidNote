import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../shared/api/client";
import type { ChatFocus, NoteTemplate, Person, SessionDetail, Tag } from "../shared/api/types";
import { UserNotes } from "../features/notes/UserNotes";
import { templateName } from "../shared/lib/templates";
import { pluralForm, useI18n } from "../shared/i18n";
import { AudioPlayer } from "../features/audio/AudioPlayer";
import { FolderSelect } from "../features/session/FolderSelect";
import { NoteDocument } from "../features/document/NoteDocument";
import { modeIcon } from "../features/command/CommandPalette";
import { SummaryPanel } from "../features/summary/SummaryPanel";
import { DockToggle, TranscriptTicker, useTranscriptDock } from "../features/transcript/TranscriptDock";
import { TranscriptList } from "../features/transcript/TranscriptList";
import { VoiceRoster } from "../features/voices/VoiceRoster";
import { VoiceTimeline } from "../features/voices/VoiceTimeline";
import { formatClock, formatDate } from "../shared/lib/format";
import { openLocalPath, parentDirectory, saveBlob } from "../shared/lib/saveFile";
import { buildRoster, countWords, mergeVoicesByPerson } from "../shared/lib/voices";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { Icon } from "../shared/ui/Icon";
import { Button } from "../shared/ui/primitives";
import { SessionTitle } from "../shared/ui/SessionTitle";
import { useToast } from "../shared/ui/Toast";

interface SessionPageProps {
  sessionId: string;
  seekTo?: number | null;
  templates?: NoteTemplate[];
  notesRevision?: number;
  voicesRevision?: number;
  voiceReady: boolean;
  voiceDownloading: boolean;
  onDownloadVoice: () => void;
  onDeleted: () => void;
  onRenamed?: (title: string) => void;
  onTagsChanged?: () => void;
  languageLocked?: boolean;
  onAsk?: (focus: ChatFocus) => void;
  summaryBusySessionId?: string | null;
  summaryRevision?: number;
}

type ExportFormat = "markdown" | "pdf" | "docx" | "json";
type SideTab = "doc" | "voices";

const EXPORT_OPTIONS: { format: ExportFormat; label: string; ext: string; filter: string }[] = [
  { format: "markdown", label: "Markdown", ext: "md", filter: "Markdown" },
  { format: "pdf", label: "PDF", ext: "pdf", filter: "PDF" },
  { format: "docx", label: "DOCX", ext: "docx", filter: "Word" },
  { format: "json", label: "JSON", ext: "json", filter: "JSON" },
];

export function SessionPage({
  sessionId,
  seekTo = null,
  templates = [],
  notesRevision = 0,
  voicesRevision = 0,
  voiceReady,
  voiceDownloading,
  onDownloadVoice,
  onDeleted,
  onRenamed,
  onTagsChanged,
  languageLocked = false,
  onAsk,
  summaryBusySessionId = null,
  summaryRevision = 0,
}: SessionPageProps) {
  const { t, locale } = useI18n();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [query, setQuery] = useState("");
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [catalog, setCatalog] = useState<Tag[]>([]);
  const [assigning, setAssigning] = useState(false);
  const [seekMs, setSeekMs] = useState<number | null>(null);
  const [activeMs, setActiveMs] = useState<number | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [side, setSide] = useState<SideTab>("doc");
  const [citeMs, setCiteMs] = useState<number | null>(null);
  const [dockMin, toggleDock] = useTranscriptDock();
  const [refining, setRefining] = useState(false);
  const [recipesOpen, setRecipesOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirm();
  const toast = useToast();

  const reload = useCallback(async () => {
    setDetail(await api.session(sessionId));
  }, [sessionId]);

  const loadPeople = useCallback(async () => {
    setPeople(await api.people());
  }, []);

  const lastSummaryRevision = useRef(summaryRevision);
  useEffect(() => {
    if (summaryRevision === lastSummaryRevision.current) return;
    lastSummaryRevision.current = summaryRevision;
    void reload();
  }, [summaryRevision, reload]);

  const cite = (ms: number) => {
    if (dockMin) toggleDock();
    setCiteMs(ms + Math.random() * 0.5);
    setActiveMs(ms);
    if (detail?.session.has_audio) setSeekMs(ms);
  };

  useEffect(() => {
    void reload();
    void loadPeople();
    void api.tags().then(setCatalog);
    setSeekMs(null);
    setActiveMs(null);
  }, [sessionId, reload, loadPeople]);

  useEffect(() => {
    if (seekTo !== null && seekTo !== undefined) setSeekMs(seekTo);
  }, [seekTo, sessionId]);

  const lastRevision = useRef(voicesRevision);
  useEffect(() => {
    if (voicesRevision === lastRevision.current) return;
    lastRevision.current = voicesRevision;
    void reload();
  }, [voicesRevision, reload]);

  useEffect(() => {
    if (!exportOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(event.target as Node)) setExportOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExportOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [exportOpen]);

  const merged = useMemo(() => mergeVoicesByPerson(detail?.segments ?? []), [detail?.segments]);
  const segments = merged.segments;
  const roster = useMemo(() => buildRoster(segments, people), [segments, people]);
  const words = useMemo(() => countWords(segments), [segments]);



  if (!detail) {
    return <div className="page-loading">{t("session.loading")}</div>;
  }

  const filtered = query.trim()
    ? segments.filter((item) => item.text.toLowerCase().includes(query.trim().toLowerCase()))
    : segments;

  const rename = async (title: string) => {
    const updated = await api.renameSession(sessionId, title);
    setDetail({ ...detail, session: updated });
    onRenamed?.(updated.title);
  };

  const generate = async (chosen?: string | null) => {
    setLoadingSummary(true);
    setSummaryError(null);
    try {
      const summary = await api.summarize(sessionId, chosen);
      setDetail((current) =>
        current
          ? {
              ...current,
              summary,
              session: chosen === undefined ? current.session : { ...current.session, template_id: chosen },
            }
          : current,
      );
      setSide("doc");
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : t("session.noteFail"));
    } finally {
      setLoadingSummary(false);
    }
  };

  const exportFile = async (format: ExportFormat) => {
    const option = EXPORT_OPTIONS.find((item) => item.format === format);
    if (!option) return;
    setExportOpen(false);
    setExportBusy(true);
    try {
      const blob = await api.exportSession(sessionId, format);
      const suggestedName = `${detail.session.title}.${option.ext}`;
      const result = await saveBlob(blob, suggestedName, [{ name: option.filter, extensions: [option.ext] }]);
      if (result.status === "cancelled") return;
      if (result.status === "error") {
        toast.push({ tone: "error", title: t("session.exportFail"), description: result.message });
        return;
      }
      toast.push({
        tone: "success",
        title: t("session.fileSaved"),
        description: suggestedName,
        action: result.path
          ? { label: t("session.openFolder"), onClick: () => void openLocalPath(parentDirectory(result.path ?? "")) }
          : undefined,
      });
    } catch (err) {
      toast.push({
        tone: "error",
        title: t("session.exportFail"),
        description: err instanceof Error ? err.message : t("session.exportFailBody"),
      });
    } finally {
      setExportBusy(false);
    }
  };

  const remove = async () => {
    const ok = await confirm({
      title: t("session.deleteTitle", { title: detail.session.title }),
      description: t("session.deleteBody"),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    await api.deleteSession(sessionId);
    onDeleted();
  };

  const assignVoice = async (cluster: string, payload: { person_id?: string | null; name?: string }) => {
    let result = await api.assignVoice(sessionId, cluster, payload);
    for (const other of (merged.members.get(cluster) ?? [cluster]).filter((item) => item !== cluster)) {
      result = await api.assignVoice(sessionId, other, payload);
    }
    setDetail((current) => (current ? { ...current, segments: result.segments } : current));
    await loadPeople();
  };

  const refine = async () => {
    setRefining(true);
    try {
      const result = await api.refineVoices(sessionId);
      setDetail((current) => (current ? { ...current, segments: result.segments } : current));
    } finally {
      setRefining(false);
    }
  };

  const mode = detail.session.capture_mode ?? "meeting";

  return (
    <div className="page session">
      <header className="page-head">
        <div className="page-head-copy">
          <SessionTitle value={detail.session.title} onCommit={rename} />
          <p className="session-meta">
            <span>
              <Icon name={modeIcon(mode)} size={13} />
              {t(`live.${mode}`)}
            </span>
            <span>{formatDate(detail.session.started_at)}</span>
            <span>{formatClock(detail.session.duration_ms)}</span>
            {roster.length ? <span>{t("voices.count", { count: roster.length })}</span> : null}
            {words ? <span>{t("console.words", { count: words })}</span> : null}
            {detail.session.language ? <span>{detail.session.language.toUpperCase()}</span> : null}
          </p>
        </div>
        <div className="page-actions">
          <FolderSelect
            sessionId={sessionId}
            tags={detail.session.tags ?? []}
            catalog={catalog}
            onChange={(tags) => {
              setDetail({ ...detail, session: { ...detail.session, tags } });
              void api.tags().then(setCatalog);
              onTagsChanged?.();
            }}
          />
          {onAsk ? (
            <Button variant="quiet" onClick={() => onAsk({ sessionId, sessionTitle: detail.session.title })}>
              <Icon name="chat" size={15} />
              {t("transcript.ask")}
            </Button>
          ) : null}
          {onAsk && templates.some((item) => item.kind === "recipe") ? (
            <div className="export-menu">
              <Button variant="quiet" aria-expanded={recipesOpen} onClick={() => setRecipesOpen((open) => !open)}>
                <Icon name="spark" size={15} />
                {t("recipes.title")}
              </Button>
              {recipesOpen ? (
                <div className="export-menu-list" role="menu">
                  {templates
                    .filter((item) => item.kind === "recipe")
                    .map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setRecipesOpen(false);
                          onAsk({ sessionId, sessionTitle: detail.session.title, prompt: item.body });
                        }}
                      >
                        {templateName(item)}
                      </button>
                    ))}
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="export-menu" ref={exportRef}>
            <Button disabled={exportBusy} aria-expanded={exportOpen} aria-haspopup="menu" onClick={() => setExportOpen((open) => !open)}>
              <Icon name="export" size={15} />
              {exportBusy ? t("session.exporting") : t("session.export")}
            </Button>
            {exportOpen && !exportBusy ? (
              <div className="export-menu-list" role="menu">
                {EXPORT_OPTIONS.map((option) => (
                  <button key={option.format} type="button" role="menuitem" onClick={() => void exportFile(option.format)}>
                    {option.label}
                    <small>.{option.ext}</small>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <Button variant="danger" onClick={() => void remove()} aria-label={t("common.delete")} title={t("common.delete")}>
            <Icon name="trash" size={15} />
          </Button>
        </div>
      </header>

      {summaryError ? <p className="banner">{summaryError}</p> : null}


      {detail.session.has_audio || detail.segments.length ? (
      <section className="panel playback">
        {detail.session.has_audio ? (
          <AudioPlayer sessionId={sessionId} seekMs={seekMs} onSeeked={() => setSeekMs(null)} onTimeMs={setActiveMs} />
        ) : null}
        <VoiceTimeline
          segments={segments}
          roster={roster}
          durationMs={detail.session.duration_ms}
          playheadMs={detail.session.has_audio ? activeMs : null}
          onSeek={detail.session.has_audio ? (ms) => setSeekMs(ms) : undefined}
        />
      </section>
      ) : null}

      <div className={`workspace is-ai-first${dockMin ? " is-dock-min" : ""}`}>
        <section className="panel transcript-panel">
          <div className="panel-head">
            <div className="panel-title">
              <h2>{t("live.transcript")}</h2>
              <span className="panel-meta">
                {t(`transcript.${pluralForm(locale, detail.segments.length)}`, { count: detail.segments.length })}
              </span>
            </div>
            <DockToggle min={dockMin} onToggle={toggleDock} />
            {!dockMin ? (
              <label className="search-field">
                <Icon name="search" size={15} />
                <input
                  placeholder={t("session.search")}
                  aria-label={t("session.searchAria")}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
            ) : null}
          </div>
          {detail.session.transcript_purged_at ? (
            <p className="purged-note">
              <Icon name="shield" size={14} />
              {t("retention.purgedNote")}
            </p>
          ) : null}
          {dockMin ? (
            <TranscriptTicker segments={segments} people={people} live={false} onExpand={toggleDock} />
          ) : (
          <TranscriptList
            focusMs={citeMs}
            segments={filtered}
            query={query}
            emptyHint={query ? t("palette.empty") : t("transcript.emptyPast")}
            emptyDetail={null}
            people={people}
            languageLocked={languageLocked}
            sessionId={sessionId}
            assigningAll={assigning}
            activeMs={activeMs}
            onSeek={detail.session.has_audio ? (ms) => setSeekMs(ms) : undefined}
            onAskSelected={
              onAsk
                ? (segment) =>
                    onAsk({ sessionId, sessionTitle: detail.session.title, segmentId: segment.id, excerpt: segment.text })
                : undefined
            }
            onAssignAll={
              roster.length
                ? undefined
                : async () => {
                    setAssigning(true);
                    try {
                      const next = await api.assignSpeakers(sessionId);
                      setDetail((current) => (current ? { ...current, segments: next } : current));
                    } finally {
                      setAssigning(false);
                    }
                  }
            }
            onPatchSegment={async (segmentId, payload) => {
              const updated = await api.assignSegmentSpeaker(sessionId, segmentId, payload);
              const speakerChanged = payload.speaker_id !== undefined || Boolean(payload.name);
              if (speakerChanged) {
                await reload();
                if (payload.name) await loadPeople();
                return;
              }
              setDetail((current) =>
                current
                  ? { ...current, segments: current.segments.map((item) => (item.id === updated.id ? updated : item)) }
                  : current,
              );
            }}
          />
          )}
        </section>
        <aside className="panel side-panel">
          <div className="tabs" role="tablist">
            <button type="button" role="tab" aria-selected={side === "doc"} className={side === "doc" ? "is-on" : ""} onClick={() => setSide("doc")}>
              <Icon name="spark" size={15} />
              {t("doc.tab")}
            </button>
            <button type="button" role="tab" aria-selected={side === "voices"} className={side === "voices" ? "is-on" : ""} onClick={() => setSide("voices")}>
              <Icon name="voice" size={15} />
              {t("voices.title")}
              {roster.length ? <span className="tab-count">{roster.length}</span> : null}
            </button>
          </div>
          {side === "doc" ? (
            <div className="side-body">
              <NoteDocument
                aiFirst={Boolean(detail.summary)}
                engineRevision={summaryRevision}
                notes={
                  <UserNotes
                    sessionId={sessionId}
                    recording={false}
                    momentMs={activeMs}
                    revision={notesRevision + summaryRevision}
                    onSeek={cite}
                    onTasksChanged={onTagsChanged}
                    onAsk={onAsk ? (text) => onAsk({ sessionId, sessionTitle: detail.session.title, prompt: text }) : undefined}
                  />
                }
                aiNote={
                  <SummaryPanel
                    summary={detail.summary}
                    loading={loadingSummary || summaryBusySessionId === sessionId}
                    disabled={false}
                    title={detail.session.title}
                    captureMode={mode}
                    templates={templates}
                    templateId={detail.session.template_id ?? null}
                    onGenerate={(chosen) => void generate(chosen)}
                    onCite={cite}
                    onSaveNote={async (markdown) => {
                      const summary = await api.saveNote(sessionId, markdown);
                      setDetail({ ...detail, summary });
                    }}
                  />
                }
              />
            </div>
          ) : (
            <div className="side-body">
              <VoiceRoster
                roster={roster}
                people={people}
                engineReady={voiceReady}
                refining={refining}
                onAssign={assignVoice}
                onRefine={() => void refine()}
                onFocusVoice={detail.session.has_audio ? (voice) => setSeekMs(voice.firstMs) : undefined}
                onDownloadEngine={onDownloadVoice}
                engineBusy={voiceDownloading}
              />
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
