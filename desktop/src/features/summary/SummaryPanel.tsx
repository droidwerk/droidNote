import { useEffect, useState } from "react";

import type { CaptureMode, Summary } from "../../shared/api/types";
import { tr, useT } from "../../shared/i18n";
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

export function SummaryPanel({
  summary,
  loading,
  disabled,
  title,
  engineLabel,
  captureMode = "meeting",
  onGenerate,
  onSaveNote,
}: SummaryPanelProps) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const sessionTitle = title ?? t("summary.session");
  const engine = engineLabel ?? t("engine.defaultEngine");
  const seed = summary ? (summary.notes_markdown?.trim() ? summary.notes_markdown : summaryToMarkdown(sessionTitle, summary)) : "";
  const [draft, setDraft] = useState(seed);
  const [saving, setSaving] = useState(false);
  const labels = {
    heading: t(`summary.${captureMode}Heading`),
    emptyTitle: t(`summary.${captureMode}EmptyTitle`),
    emptyBody: t(`summary.${captureMode}EmptyBody`),
  };

  useEffect(() => {
    setDraft(seed);
  }, [summary?.id, sessionTitle, seed]);

  const copyMarkdown = async () => {
    if (!summary) return;
    const ok = await copyToClipboard(draft || summaryToMarkdown(sessionTitle, summary));
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
              {copied ? t("common.copied") : t("common.copy")}
            </Button>
          ) : null}
          {summary && onSaveNote ? (
            <Button size="sm" disabled={saving} onClick={() => void save()}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          ) : null}
          <Button size="sm" variant="primary" disabled={disabled || loading} onClick={onGenerate}>
            {loading ? t("summary.generating") : summary ? t("summary.regenerating") : t("summary.generate")}
          </Button>
        </div>
      </div>
      {!summary && loading ? (
        <div className="note-empty">
          <div>
            <strong>{t("summary.generatingTitle")}</strong>
            <p>{t("summary.generatingBody")}</p>
          </div>
        </div>
      ) : !summary ? (
        <div className="note-empty">
          <div>
            <strong>{labels.emptyTitle}</strong>
            <p>{labels.emptyBody}</p>
          </div>
          <p className="muted">
            {t("summary.usesEngine", { engine })}
          </p>
        </div>
      ) : (
        <NoteEditor key={summary.id} content={seed} onChange={setDraft} />
      )}
    </section>
  );
}

function formatAction(item: { text: string; owner?: string | null; due?: string | null }): string {
  const parts = [item.text, item.owner ?? tr("summary.noOwner")];
  if (item.due) parts.push(item.due);
  return parts.join(" — ");
}

export function summaryToMarkdown(title: string, summary: Summary): string {
  if (summary.notes_markdown?.trim()) return summary.notes_markdown;
  const lines = [`# ${title}`, ""];
  if (summary.overview) {
    lines.push(`## ${tr("summary.overview")}`, "", summary.overview, "");
  }
  const topics = summary.topics?.length
    ? summary.topics
    : summary.highlights.length
      ? [{ title: tr("summary.happened"), points: summary.highlights }]
      : [];
  if (topics.length) {
    lines.push(`## ${tr("summary.topics")}`, "");
    for (const topic of topics) {
      if (topic.title) lines.push(`### ${topic.title}`);
      lines.push(...topic.points.map((point) => `- ${point}`), "");
    }
  }
  lines.push(`## ${tr("summary.decisions")}`, "");
  lines.push(...(summary.decisions.length ? summary.decisions.map((item) => `- ${item}`) : ["- —"]));
  lines.push("", `## ${tr("summary.actions")}`, "");
  lines.push(
    ...(summary.action_items.length
      ? summary.action_items.map((item) => `- [ ] ${formatAction(item)}`)
      : ["- —"]),
  );
  const open = summary.open_items ?? [];
  lines.push("", `## ${tr("summary.openItems")}`, "");
  lines.push(...(open.length ? open.map((item) => `- ${item}`) : ["- —"]));
  return lines.join("\n") + "\n";
}
