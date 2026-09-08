import { useEffect, useState } from "react";

import { api } from "../shared/api/client";
import type { Person, SessionDetail, Tag } from "../shared/api/types";
import { AudioPlayer } from "../features/audio/AudioPlayer";
import { SessionTags } from "../features/session/SessionTags";
import { TranscriptList } from "../features/transcript/TranscriptList";
import { SummaryPanel } from "../features/summary/SummaryPanel";
import { Button, PageHeader } from "../shared/ui/primitives";
import { SessionTitle } from "../shared/ui/SessionTitle";
import { formatDate } from "../shared/lib/format";

interface SessionPageProps {
  sessionId: string;
  onDeleted: () => void;
  onRenamed?: (title: string) => void;
  onTagsChanged?: () => void;
  languageLocked?: boolean;
}

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
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    void api.session(sessionId).then((item) => {
      setDetail(item);
    });
    void api.people().then(setPeople);
    void api.tags().then(setCatalog);
    setSeekMs(null);
    setActiveMs(null);
  }, [sessionId]);

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
    setExportError(null);
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

  const exportFile = async (format: "markdown" | "pdf" | "docx") => {
    setExportError(null);
    try {
      const blob = await api.exportSession(sessionId, format);
      const suffix = format === "markdown" ? "md" : format;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${detail.session.title}.${suffix}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Falha ao exportar");
    }
  };

  const remove = async () => {
    await api.deleteSession(sessionId);
    onDeleted();
  };

  return (
    <div className="container live">
      <PageHeader
        eyebrow="Arquivo da conversa"
        title={<SessionTitle value={detail.session.title} onCommit={rename} />}
        description={formatDate(detail.session.started_at)}
        actions={
          <>
            <Button onClick={() => void exportFile("markdown")}>Markdown</Button>
            <Button onClick={() => void exportFile("pdf")}>PDF</Button>
            <Button onClick={() => void exportFile("docx")}>DOCX</Button>
            <Button variant="danger" onClick={() => void remove()}>
              Apagar
            </Button>
          </>
        }
      />
      {exportError ? <p className="banner">{exportError}</p> : null}
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
      <div className="session-search">
        <span aria-hidden>⌕</span>
        <input
          className="search"
          placeholder="Pesquisar nesta sessão"
          aria-label="Pesquisar nesta sessão"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <div className="workspace-grid">
        <section className="card transcript-card">
          <div className="workspace-head">
            <div>
              <p className="pretitle">Registro</p>
              <h2>Transcrição</h2>
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
