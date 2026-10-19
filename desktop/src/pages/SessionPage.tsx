import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../shared/api/client";
import type { ChatFocus, Person, SessionDetail, Tag } from "../shared/api/types";
import { pluralForm, useI18n } from "../shared/i18n";
import { AudioPlayer } from "../features/audio/AudioPlayer";
import { SessionTags } from "../features/session/SessionTags";
import { SummaryPanel } from "../features/summary/SummaryPanel";
import { TranscriptList } from "../features/transcript/TranscriptList";
import { VoiceRoster } from "../features/voices/VoiceRoster";
import { VoiceTimeline } from "../features/voices/VoiceTimeline";
import { formatClock, formatDate } from "../shared/lib/format";
import { openLocalPath, parentDirectory, saveBlob } from "../shared/lib/saveFile";
import { buildRoster, countWords } from "../shared/lib/voices";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { Icon } from "../shared/ui/Icon";
import { Button } from "../shared/ui/primitives";
import { SessionTitle } from "../shared/ui/SessionTitle";
import { useToast } from "../shared/ui/Toast";

interface SessionPageProps {
  sessionId: string;
  seekTo?: number | null;
  voicesRevision?: number;
  voiceReady: boolean;
  voiceDownloading: boolean;
  onDownloadVoice: () => void;
  onDeleted: () => void;
  onRenamed?: (title: string) => void;
  onTagsChanged?: () => void;
  languageLocked?: boolean;
  onAsk?: (focus: ChatFocus) => void;
}

type ExportFormat = "markdown" | "pdf" | "docx" | "json";
type SideTab = "note" | "voices";

const EXPORT_OPTIONS: { format: ExportFormat; label: string; ext: string; filter: string }[] = [
  { format: "markdown", label: "Markdown", ext: "md", filter: "Markdown" },
  { format: "pdf", label: "PDF", ext: "pdf", filter: "PDF" },
  { format: "docx", label: "DOCX", ext: "docx", filter: "Word" },
  { format: "json", label: "JSON", ext: "json", filter: "JSON" },
];

export function SessionPage({
  sessionId,
  seekTo = null,
  voicesRevision = 0,
  voiceReady,
  voiceDownloading,
  onDownloadVoice,
  onDeleted,
  onRenamed,
  onTagsChanged,
  languageLocked = false,
  onAsk,
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
  const [side, setSide] = useState<SideTab>("note");
  const [refining, setRefining] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirm();
  const toast = useToast();

  const reload = useCallback(async () => {
    setDetail(await api.session(sessionId));
  }, [sessionId]);

  const loadPeople = useCallback(async () => {
    setPeople(await api.people());
  }, []);

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

  const segments = detail?.segments ?? [];
  const roster = useMemo(() => buildRoster(segments, people), [segments, people]);
  const words = useMemo(() => countWords(segments), [segments]);

  useEffect(() => {
    if (roster.length > 0 && !detail?.summary) setSide("voices");
  }, [roster.length, detail?.summary]);

  if (!detail) {
    return <div className="page-loading">{t("session.loading")}</div>;
  }

  const filtered = query.trim()
    ? detail.segments.filter((item) => item.text.toLowerCase().includes(query.trim().toLowerCase()))
    : detail.segments;

  const rename = async (title: string) => {
    const updated = await api.renameSession(sessionId, title);
    setDetail({ ...detail, session: updated });
    onRenamed?.(updated.title);
  };

  const generate = async () => {
    setLoadingSummary(true);
    setSummaryError(null);
    try {
      const summary = await api.summarize(sessionId);
      setDetail((current) => (current ? { ...current, summary } : current));
      setSide("note");
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
    const result = await api.assignVoice(sessionId, cluster, payload);
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
          <span className="eyebrow">
            {t(`live.${mode}`)} · {formatDate(detail.session.started_at)}
          </span>
          <SessionTitle value={detail.session.title} onCommit={rename} />
          <dl className="meta-row">
            <div>
              <dt>{t("meta.duration")}</dt>
              <dd>{formatClock(detail.session.duration_ms)}</dd>
            </div>
            <div>
              <dt>{t("meta.voices")}</dt>
              <dd>{roster.length || "—"}</dd>
            </div>
            <div>
              <dt>{t("meta.excerpts")}</dt>
              <dd>{detail.segments.length}</dd>
            </div>
            <div>
              <dt>{t("meta.words")}</dt>
              <dd>{words}</dd>
            </div>
            {detail.session.language ? (
              <div>
                <dt>{t("meta.language")}</dt>
                <dd>{detail.session.language.toUpperCase()}</dd>
              </div>
            ) : null}
          </dl>
        </div>
        <div className="page-actions">
          {onAsk ? (
            <Button variant="quiet" onClick={() => onAsk({ sessionId, sessionTitle: detail.session.title })}>
              <Icon name="chat" size={15} />
              {t("transcript.ask")}
            </Button>
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

      <SessionTags
        sessionId={sessionId}
        tags={detail.session.tags ?? []}
        catalog={catalog}
        onChange={(tags) => {
          setDetail({ ...detail, session: { ...detail.session, tags } });
          void api.tags().then(setCatalog);
          onTagsChanged?.();
        }}
      />

      <section className="panel playback">
        {detail.session.has_audio ? (
          <AudioPlayer sessionId={sessionId} seekMs={seekMs} onSeeked={() => setSeekMs(null)} onTimeMs={setActiveMs} />
        ) : (
          <p className="muted playback-empty">{t("session.noWav")}</p>
        )}
        <VoiceTimeline
          segments={detail.segments}
          roster={roster}
          durationMs={detail.session.duration_ms}
          playheadMs={detail.session.has_audio ? activeMs : null}
          onSeek={detail.session.has_audio ? (ms) => setSeekMs(ms) : undefined}
        />
      </section>

      <div className="workspace">
        <section className="panel transcript-panel">
          <div className="panel-head">
            <div className="panel-title">
              <span className="eyebrow">01</span>
              <h2>{t("live.transcript")}</h2>
              <span className="panel-meta">
                {t(`transcript.${pluralForm(locale, detail.segments.length)}`, { count: detail.segments.length })}
              </span>
            </div>
            <label className="search-field">
              <Icon name="search" size={15} />
              <input
                placeholder={t("session.search")}
                aria-label={t("session.searchAria")}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
          </div>
          <TranscriptList
            segments={filtered}
            query={query}
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
        </section>
        <aside className="panel side-panel">
          <div className="tabs" role="tablist">
            <button type="button" role="tab" aria-selected={side === "note"} className={side === "note" ? "is-on" : ""} onClick={() => setSide("note")}>
              <Icon name="spark" size={15} />
              {t("console.notes")}
            </button>
            <button type="button" role="tab" aria-selected={side === "voices"} className={side === "voices" ? "is-on" : ""} onClick={() => setSide("voices")}>
              <Icon name="voice" size={15} />
              {t("voices.title")}
              {roster.length ? <span className="tab-count">{roster.length}</span> : null}
            </button>
          </div>
          {side === "note" ? (
            <SummaryPanel
              summary={detail.summary}
              loading={loadingSummary}
              disabled={false}
              title={detail.session.title}
              captureMode={mode}
              onGenerate={() => void generate()}
              onSaveNote={async (markdown) => {
                const summary = await api.saveNote(sessionId, markdown);
                setDetail({ ...detail, summary });
              }}
            />
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
