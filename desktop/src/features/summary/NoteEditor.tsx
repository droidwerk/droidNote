import { useEffect } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

interface NoteEditorProps {
  content: string;
  onChange: (markdown: string) => void;
  disabled?: boolean;
  /** Clique numa marca de tempo (`12:40`) leva ao momento da fala. */
  onCite?: (ms: number) => void;
}

const STAMP = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;

export function stampToMs(value: string): number | null {
  const match = STAMP.exec(value.trim());
  if (!match) return null;
  const [, a, b, c] = match;
  const parts = c !== undefined ? [Number(a), Number(b), Number(c)] : [0, Number(a), Number(b)];
  return ((parts[0] ?? 0) * 3600 + (parts[1] ?? 0) * 60 + (parts[2] ?? 0)) * 1000;
}

export function NoteEditor({ content, onChange, disabled = false, onCite }: NoteEditorProps) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: markdownToHtml(content),
    editable: !disabled,
    onUpdate: ({ editor: current }) => {
      onChange(htmlToMarkdown(current.getHTML()));
    },
  });

  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [disabled, editor]);

  return (
    <div
      className={onCite ? "note-editor has-cites" : "note-editor"}
      onClick={(event) => {
        const code = (event.target as HTMLElement).closest("code");
        if (!code || !onCite) return;
        const ms = stampToMs(code.textContent ?? "");
        if (ms !== null) onCite(ms);
      }}
    >
      <EditorContent editor={editor} />
    </div>
  );
}

function markdownToHtml(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "<p></p>";
  if (trimmed.startsWith("<")) return trimmed;
  return trimmed
    .split(/\n{2,}/)
    .map((block) => {
      const lines = block.split("\n");
      if (lines[0]?.startsWith("### ")) return `<h3>${escapeHtml(lines[0].slice(4))}</h3>${listOrP(lines.slice(1))}`;
      if (lines[0]?.startsWith("## ")) return `<h2>${escapeHtml(lines[0].slice(3))}</h2>${listOrP(lines.slice(1))}`;
      if (lines[0]?.startsWith("# ")) return `<h1>${escapeHtml(lines[0].slice(2))}</h1>${listOrP(lines.slice(1))}`;
      return listOrP(lines);
    })
    .join("");
}

function listOrP(lines: string[]): string {
  const items = lines.filter((line) => line.startsWith("- "));
  if (items.length && items.length === lines.filter(Boolean).length) {
    return `<ul>${items.map((item) => `<li>${escapeHtml(item.slice(2))}</li>`).join("")}</ul>`;
  }
  const text = lines.join(" ").trim();
  return text ? `<p>${escapeHtml(text)}</p>` : "";
}

function htmlToMarkdown(html: string): string {
  return html
    .replace(/<h1[^>]*>(.*?)<\/h1>/gi, "# $1\n\n")
    .replace(/<h2[^>]*>(.*?)<\/h2>/gi, "## $1\n\n")
    .replace(/<h3[^>]*>(.*?)<\/h3>/gi, "### $1\n\n")
    .replace(/<code[^>]*>(.*?)<\/code>/gi, "`$1`")
    .replace(/<li[^>]*>(.*?)<\/li>/gi, "- $1\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .trim();
}

function escapeHtml(value: string): string {
  // `12:40` (citação do momento) vira <code>, que a nota mostra como marca clicável.
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}
