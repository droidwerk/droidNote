import { useEffect, useRef, useState } from "react";

import { api } from "../shared/api/client";
import type { Person, SessionDetail, Tag } from "../shared/api/types";
import { AudioPlayer } from "../features/audio/AudioPlayer";
import { SessionTags } from "../features/session/SessionTags";
import { TranscriptList } from "../features/transcript/TranscriptList";
import { SummaryPanel } from "../features/summary/SummaryPanel";
import { Button, PageHeader } from "../shared/ui/primitives";
import { SessionTitle } from "../shared/ui/SessionTitle";
import { formatDate } from "../shared/lib/format";
import { openLocalPath, parentDirectory, saveBlob } from "../shared/lib/saveFile";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { useToast } from "../shared/ui/Toast";

interface SessionPageProps {
  sessionId: string;
  onDeleted: () => void;
  onRenamed?: (title: string) => void;
  onTagsChanged?: () => void;
  languageLocked?: boolean;
}

type ExportFormat = "markdown" | "pdf" | "docx" | "json";

const EXPORT_OPTIONS: { format: ExportFormat; label: string; ext: string; filter: string }[] = [
  { format: "markdown", label: "Markdown", ext: "md", filter: "Markdown" },
  { format: "pdf", label: "PDF", ext: "pdf", filter: "PDF" },
  { format: "docx", label: "DOCX", ext: "docx", filter: "Word" },
  { format: "json", label: "JSON", ext: "json", filter: "JSON" },
];

export function SessionPage({
  sessionId,
  onDeleted,
  onRenamed,
  onTagsChanged,
  languageLocked = false,
}: SessionPageProps) {
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
  const exportRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirm();
  const toast = useToast();

  useEffect(() => {
    void api.session(sessionId).then((item) => {
      setDetail(item);
    });
    void api.people().then(setPeople);
    void api.tags().then(setCatalog);
    setSeekMs(null);
    setActiveMs(null);
  }, [sessionId]);

  useEffect(() => {
    if (!exportOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(event.target as Node)) {
        setExportOpen(false);
      }
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

  if (!detail) {
    return <div className="empty-block">Carregando sessão…</div>;
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
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Falha ao gerar a nota");
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
      const result = await saveBlob(blob, suggestedName, [
        { name: option.filter, extensions: [option.ext] },
      ]);
      if (result.status === "cancelled") return;
      if (result.status === "error") {
        toast.push({ tone: "error", title: "Falha ao exportar", description: result.message });
        return;
      }
      toast.push({
        tone: "success",
        title: "Arquivo gravado",
        description: suggestedName,
        action: result.path
          ? {
              label: "Abrir pasta",
              onClick: () => void openLocalPath(parentDirectory(result.path ?? "")),
            }
          : undefined,
      });
    } catch (err) {
      toast.push({
        tone: "error",
        title: "Falha ao exportar",
        description: err instanceof Error ? err.message : "Não foi possível gerar o arquivo.",
      });
    } finally {
      setExportBusy(false);
    }
  };

  const remove = async () => {
    const ok = await confirm({
      title: `Apagar “${detail.session.title}”?`,
      description: "A transcrição, a nota e o áudio desta sessão serão removidos.",
      confirmLabel: "Apagar",
      tone: "danger",
    });
    if (!ok) return;
    await api.deleteSession(sessionId);
    onDeleted();
  };

  return (
    <div className="container live">
      <PageHeader
        title={<SessionTitle value={detail.session.title} onCommit={rename} />}
        description={formatDate(detail.session.started_at)}
        actions={
          <>
            <div className="export-menu" ref={exportRef}>
              <Button
                disabled={exportBusy}
                aria-expanded={exportOpen}
                aria-haspopup="menu"
                onClick={() => setExportOpen((open) => !open)}
              >
                {exportBusy ? "Exportando…" : "Exportar"}
              </Button>
              {exportOpen && !exportBusy ? (
                <div className="export-menu-list" role="menu">
                  {EXPORT_OPTIONS.map((option) => (
                    <button
                      key={option.format}
                      type="button"
                      role="menuitem"
                      onClick={() => void exportFile(option.format)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <Button variant="danger" onClick={() => void remove()}>
              Apagar
            </Button>
          </>
        }
      />
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
      {detail.session.has_audio ? (
        <AudioPlayer
          sessionId={sessionId}
          seekMs={seekMs}
          onSeeked={() => setSeekMs(null)}
          onTimeMs={setActiveMs}
        />
      ) : (
        <p className="muted">Esta sessão não tem WAV neste PC. Ligue a opção em Preferências na próxima captura.</p>
      )}
      <div className="workspace-grid">
        <section className="card transcript-card">
          <div className="workspace-head">
            <div>
              <h2>Transcrição</h2>
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
                placeholder="Pesquisar"
                aria-label="Pesquisar nesta sessão"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          </div>
          <TranscriptList
            segments={filtered}
            query={query}
            people={people}
            languageLocked={languageLocked}
            sessionId={sessionId}
            assigningAll={assigning}
            activeMs={activeMs}
            onSeek={(ms) => setSeekMs(ms)}
            onAssignAll={async () => {
              setAssigning(true);
              try {
                const segments = await api.assignSpeakers(sessionId);
                setDetail((current) => (current ? { ...current, segments } : current));
              } finally {
                setAssigning(false);
              }
            }}
            onPatchSegment={async (segmentId, payload) => {
              const updated = await api.assignSegmentSpeaker(sessionId, segmentId, payload);
              const speakerChanged = payload.speaker_id !== undefined || Boolean(payload.name);
              if (speakerChanged) {
                const next = await api.session(sessionId);
                setDetail(next);
                if (payload.name) setPeople(await api.people());
                return;
              }
              setDetail((current) =>
                current
                  ? {
                      ...current,
                      segments: current.segments.map((item) => (item.id === updated.id ? updated : item)),
                    }
                  : current,
              );
            }}
          />
        </section>
        <SummaryPanel
          summary={detail.summary}
          loading={loadingSummary}
          disabled={false}
          title={detail.session.title}
          captureMode={detail.session.capture_mode ?? "meeting"}
          onGenerate={() => void generate()}
          onSaveNote={async (markdown) => {
            const summary = await api.saveNote(sessionId, markdown);
            setDetail({ ...detail, summary });
          }}
        />
      </div>
    </div>
  );
}
