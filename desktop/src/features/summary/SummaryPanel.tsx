import { useEffect, useState } from "react";

import type { CaptureMode, Summary } from "../../shared/api/types";
import { copyToClipboard } from "../../shared/lib/format";
import { Button } from "../../shared/ui/primitives";
import { NoteEditor } from "./NoteEditor";

interface SummaryPanelProps {
  summary: Summary | null;
  loading: boolean;
  disabled: boolean;
  title?: string;
  engineLabel?: string;
  captureMode?: CaptureMode;
  onGenerate: () => void;
  onSaveNote?: (markdown: string) => Promise<void>;
}

const COPY: Record<CaptureMode, { heading: string; emptyTitle: string; emptyBody: string }> = {
  meeting: {
    heading: "Ata da conversa",
    emptyTitle: "Sua ata será organizada aqui",
    emptyBody: "Gere um resumo com assuntos, decisões, responsáveis e pendências.",
  },
  lecture: {
    heading: "Caderno da aula",
    emptyTitle: "O caderno da aula aparece aqui",
    emptyBody: "Gere um resumo com temas, conceitos e o que revisar depois.",
  },
  dictation: {
    heading: "Anotação",
    emptyTitle: "Sua anotação será organizada aqui",
    emptyBody: "Gere um caderno com ideias, lembretes e tarefas que você ditou.",
  },
};

export function SummaryPanel({
  summary,
  loading,
  disabled,
  title = "Sessão",
  engineLabel = "o motor escolhido nas preferências",
  captureMode = "meeting",
  onGenerate,
  onSaveNote,
}: SummaryPanelProps) {
  const [copied, setCopied] = useState(false);
  const seed = summary ? (summary.notes_markdown?.trim() ? summary.notes_markdown : summaryToMarkdown(title, summary)) : "";
  const [draft, setDraft] = useState(seed);
  const [saving, setSaving] = useState(false);
  const labels = COPY[captureMode];

  useEffect(() => {
    setDraft(seed);
  }, [summary?.id, title, seed]);

  const copyMarkdown = async () => {
    if (!summary) return;
    const ok = await copyToClipboard(draft || summaryToMarkdown(title, summary));
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  const save = async () => {
    if (!onSaveNote) return;
    setSaving(true);
    try {
      await onSaveNote(draft);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card summary">
      <div className="summary-head">
        <h2>{labels.heading}</h2>
        <div className="summary-actions">
          {summary ? (
            <Button size="sm" variant="quiet" onClick={() => void copyMarkdown()}>
              {copied ? "Copiado" : "Copiar"}
            </Button>
          ) : null}
          {summary && onSaveNote ? (
            <Button size="sm" disabled={saving} onClick={() => void save()}>
              {saving ? "Salvando…" : "Salvar"}
            </Button>
          ) : null}
          <Button size="sm" variant="primary" disabled={disabled || loading} onClick={onGenerate}>
            {loading ? "Gerando…" : summary ? "Regenerar" : "Gerar nota"}
          </Button>
        </div>
      </div>
      {!summary && loading ? (
        <div className="note-empty">
          <div>
            <strong>Gerando nota…</strong>
            <p>O motor está organizando a transcrição. Pode levar um instante.</p>
          </div>
        </div>
      ) : !summary ? (
        <div className="note-empty">
          <div>
            <strong>{labels.emptyTitle}</strong>
            <p>{labels.emptyBody}</p>
          </div>
          <p className="muted">
            Usa {engineLabel}. Você pode corrigir a transcrição antes de gerar.
          </p>
        </div>
      ) : (
        <NoteEditor key={summary.id} content={seed} onChange={setDraft} />
      )}
    </section>
  );
}

function formatAction(item: { text: string; owner?: string | null; due?: string | null }): string {
  const parts = [item.text, item.owner ?? "sem responsável"];
  if (item.due) parts.push(item.due);
  return parts.join(" — ");
}

export function summaryToMarkdown(title: string, summary: Summary): string {
  if (summary.notes_markdown?.trim()) return summary.notes_markdown;
  const lines = [`# ${title}`, ""];
  if (summary.overview) {
    lines.push("## Resumo executivo", "", summary.overview, "");
  }
  const topics = summary.topics?.length
    ? summary.topics
    : summary.highlights.length
      ? [{ title: "O que aconteceu", points: summary.highlights }]
      : [];
  if (topics.length) {
    lines.push("## Assuntos discutidos", "");
    for (const topic of topics) {
      if (topic.title) lines.push(`### ${topic.title}`);
      lines.push(...topic.points.map((point) => `- ${point}`), "");
    }
  }
  lines.push("## Decisões", "");
  lines.push(...(summary.decisions.length ? summary.decisions.map((item) => `- ${item}`) : ["- —"]));
  lines.push("", "## Ações", "");
  lines.push(
    ...(summary.action_items.length
      ? summary.action_items.map((item) => `- [ ] ${formatAction(item)}`)
      : ["- —"]),
  );
  const open = summary.open_items ?? [];
  lines.push("", "## Pendências", "");
  lines.push(...(open.length ? open.map((item) => `- ${item}`) : ["- —"]));
  return lines.join("\n") + "\n";
}
