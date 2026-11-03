import { Fragment, useState, type ReactNode } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

import { openExternal } from "../lib/openExternal";
import { MiniChart, parseChartSpec } from "./MiniChart";

interface MarkdownProps {
  text: string;
  /** Marca de tempo (12:40) vira um elemento clicável; sem isso fica como texto. */
  renderStamp?: (stamp: string) => ReactNode;
  /** Citação numerada [3] vira um elemento clicável; sem isso fica como texto. */
  renderCite?: (index: number) => ReactNode;
  /** Rótulo do botão que mostra os valores de um gráfico em tabela. */
  chartTableLabel?: string;
  /** Bloco ```prompt (modo Resolver) vira um cartão com botão de copiar. */
  promptLabels?: { title: string; copy: string; copied: string };
  className?: string;
}

type Inline = {
  renderStamp?: (stamp: string) => ReactNode;
  renderCite?: (index: number) => ReactNode;
};

type Align = "left" | "center" | "right" | null;

type Block =
  | { kind: "p"; text: string }
  | { kind: "h"; level: number; text: string }
  | { kind: "code"; text: string; lang: string }
  | { kind: "quote"; text: string }
  | { kind: "rule" }
  | { kind: "math"; text: string }
  | { kind: "table"; header: string[]; align: Align[]; rows: string[][] }
  | { kind: "list"; ordered: boolean; items: { text: string; level: number }[] };

const STAMP = /\b(\d{1,2}:\d{2}(?::\d{2})?)\b/g;
// Ordem importa: fórmula e código antes de negrito/itálico, para "$a*b$" não virar itálico.
const INLINE =
  /(\$\$[^$]+\$\$|\\\([\s\S]+?\\\)|\$(?!\s)[^$\n]*?[^\s$]\$(?!\d)|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
const TABLE_SEP = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/;
const PLAIN_FENCES = new Set(["", "text", "txt", "plaintext", "markdown", "md"]);

/** Markdown das respostas da IA renderizado sem HTML cru: títulos, listas, tabelas, fórmulas (KaTeX), código e marcas de tempo. */
export function Markdown({ text, renderStamp, renderCite, chartTableLabel = "Table", promptLabels, className }: MarkdownProps) {
  const blocks = parseBlocks(text);
  const inl: Inline = { renderStamp, renderCite };
  return (
    <div className={className ? `md ${className}` : "md"}>
      {blocks.map((block, index) => (
        <Fragment key={index}>{renderBlock(block, inl, chartTableLabel, promptLabels)}</Fragment>
      ))}
    </div>
  );
}

/** Prompt pronto para colar num agente de código: cartão com botão de copiar. */
function PromptCard({ text, labels }: { text: string; labels: { title: string; copy: string; copied: string } }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* sem clipboard: o texto continua selecionável */
    }
  };
  return (
    <div className="md-prompt">
      <div className="md-prompt-head">
        <strong>{labels.title}</strong>
        <button type="button" onClick={() => void copy()}>
          {copied ? labels.copied : labels.copy}
        </button>
      </div>
      <pre>
        <code>{text}</code>
      </pre>
    </div>
  );
}

function renderBlock(block: Block, inl: Inline, chartTableLabel: string, promptLabels?: MarkdownProps["promptLabels"]): ReactNode {
  if (block.kind === "h") {
    const level = Math.min(Math.max(block.level, 1), 4);
    const content = inline(block.text, inl);
    if (level === 1) return <h3>{content}</h3>;
    if (level === 2) return <h4>{content}</h4>;
    return <h5>{content}</h5>;
  }
  if (block.kind === "code") {
    if (["math", "latex", "tex", "katex"].includes(block.lang)) return math(block.text, true);
    if (block.lang === "chart") {
      const spec = parseChartSpec(block.text);
      if (spec) return <MiniChart spec={spec} tableLabel={chartTableLabel} />;
    }
    // Prompt pronto: o bloco ```prompt, ou um bloco de texto longo sem linguagem de código
    // (modelos locais às vezes trocam a marca por ```text ou ```markdown).
    if (promptLabels && (block.lang === "prompt" || (PLAIN_FENCES.has(block.lang) && block.text.length > 300))) {
      return <PromptCard text={block.text} labels={promptLabels} />;
    }
    return (
      <pre>
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.kind === "math") return math(block.text, true);
  if (block.kind === "rule") return <hr />;
  if (block.kind === "quote") return <blockquote>{inline(block.text, inl)}</blockquote>;
  if (block.kind === "list") return renderList(block.items, block.ordered, inl);
  if (block.kind === "table") return renderTable(block, inl);
  return <p>{inline(block.text, inl)}</p>;
}

function renderTable(block: { header: string[]; align: Align[]; rows: string[][] }, inl: Inline): ReactNode {
  const style = (index: number) => {
    const align = block.align[index];
    return align ? { textAlign: align } : undefined;
  };
  return (
    <div className="md-table">
      <table>
        <thead>
          <tr>
            {block.header.map((cell, index) => (
              <th key={index} style={style(index)}>
                {inline(cell, inl)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {block.header.map((_, index) => (
                <td key={index} style={style(index)}>
                  {inline(row[index] ?? "", inl)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderList(items: { text: string; level: number }[], ordered: boolean, inl: Inline): ReactNode {
  // Recuo vira sublista: cada nível abre um <ul>/<ol> dentro do item anterior.
  const build = (start: number, level: number): [ReactNode, number] => {
    const children: ReactNode[] = [];
    let index = start;
    while (index < items.length && items[index]!.level >= level) {
      const item = items[index]!;
      if (item.level > level) {
        const [nested, next] = build(index, item.level);
        const last = children.length - 1;
        children[last] = (
          <li key={`n${index}`}>
            {(children[last] as { props: { children: ReactNode } }).props.children}
            {nested}
          </li>
        );
        index = next;
        continue;
      }
      children.push(<li key={index}>{inline(item.text, inl)}</li>);
      index += 1;
    }
    const List = ordered ? "ol" : "ul";
    return [<List key={`l${start}`}>{children}</List>, index];
  };
  return build(0, items[0]?.level ?? 0)[0];
}

/** Fórmula LaTeX via KaTeX. Erro de sintaxe mostra a fórmula em vermelho em vez de quebrar a resposta. */
function math(source: string, display: boolean): ReactNode {
  const html = katex.renderToString(source.trim(), {
    displayMode: display,
    throwOnError: false,
    strict: "ignore",
    output: "htmlAndMathml",
  });
  return display ? (
    <div className="md-math is-block" dangerouslySetInnerHTML={{ __html: html }} />
  ) : (
    <span className="md-math" dangerouslySetInnerHTML={{ __html: html }} />
  );
}

function inline(text: string, inl: Inline): ReactNode[] {
  const { renderStamp } = inl;
  const out: ReactNode[] = [];
  text.split(INLINE).forEach((piece, index) => {
    if (!piece) return;
    if (piece.startsWith("$$") && piece.endsWith("$$") && piece.length > 4) out.push(<Fragment key={index}>{math(piece.slice(2, -2), false)}</Fragment>);
    else if (piece.startsWith("\\(") && piece.endsWith("\\)")) out.push(<Fragment key={index}>{math(piece.slice(2, -2), false)}</Fragment>);
    else if (piece.startsWith("$") && piece.endsWith("$") && piece.length > 2) out.push(<Fragment key={index}>{math(piece.slice(1, -1), false)}</Fragment>);
    else if (piece.startsWith("**") && piece.endsWith("**")) out.push(<strong key={index}>{cites(piece.slice(2, -2), inl)}</strong>);
    else if (piece.startsWith("__") && piece.endsWith("__")) out.push(<strong key={index}>{cites(piece.slice(2, -2), inl)}</strong>);
    else if (piece.startsWith("`") && piece.endsWith("`")) out.push(<code key={index}>{stampsInCode(piece.slice(1, -1), renderStamp)}</code>);
    else if (piece.startsWith("[") && piece.endsWith(")")) out.push(link(piece, index));
    else if ((piece.startsWith("*") && piece.endsWith("*")) || (piece.startsWith("_") && piece.endsWith("_")))
      out.push(<em key={index}>{cites(piece.slice(1, -1), inl)}</em>);
    else out.push(<Fragment key={index}>{cites(piece, inl)}</Fragment>);
  });
  return out;
}

const CITE = /\[(\d{1,2})\]/g;

/** "[3]" e "[2][5]" no texto viram marcas clicáveis (só quando há renderCite). */
function cites(text: string, inl: Inline): ReactNode {
  if (!inl.renderCite) return stamps(text, inl.renderStamp);
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CITE)) {
    if (match.index === undefined) continue;
    parts.push(<Fragment key={`t${match.index}`}>{stamps(text.slice(last, match.index), inl.renderStamp)}</Fragment>);
    parts.push(<Fragment key={`c${match.index}`}>{inl.renderCite(Number(match[1]))}</Fragment>);
    last = match.index + match[0].length;
  }
  if (!parts.length) return stamps(text, inl.renderStamp);
  parts.push(<Fragment key="tail">{stamps(text.slice(last), inl.renderStamp)}</Fragment>);
  return parts;
}

function link(piece: string, key: number): ReactNode {
  const match = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(piece);
  if (!match) return <Fragment key={key}>{piece}</Fragment>;
  const href = match[2] ?? "";
  if (!/^https?:\/\//i.test(href)) return <Fragment key={key}>{match[1]}</Fragment>;
  // No app (Tauri) o link abre no navegador do sistema; nunca navega a janela do DroidNote.
  return (
    <a
      key={key}
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      onClick={(event) => {
        event.preventDefault();
        void openExternal(href);
      }}
    >
      {match[1]}
    </a>
  );
}

function stampsInCode(text: string, renderStamp?: (stamp: string) => ReactNode): ReactNode {
  // A ata escreve a marca como `12:40`: dentro de código ela ainda vira clicável.
  if (renderStamp && /^\d{1,2}:\d{2}(?::\d{2})?$/.test(text.trim())) return renderStamp(text.trim());
  return text;
}

function stamps(text: string, renderStamp?: (stamp: string) => ReactNode): ReactNode {
  if (!renderStamp) return text;
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(STAMP)) {
    if (match.index === undefined) continue;
    parts.push(text.slice(last, match.index));
    parts.push(<Fragment key={match.index}>{renderStamp(match[1] ?? "")}</Fragment>);
    last = match.index + match[0].length;
  }
  if (!parts.length) return text;
  parts.push(text.slice(last));
  return parts;
}

function splitRow(line: string): string[] {
  let row = line.trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
  const cells: string[] = [];
  let current = "";
  for (let index = 0; index < row.length; index += 1) {
    const char = row[index];
    if (char === "\\" && row[index + 1] === "|") {
      current += "|";
      index += 1;
    } else if (char === "|") {
      cells.push(current.trim());
      current = "";
    } else current += char;
  }
  cells.push(current.trim());
  return cells;
}

function alignments(line: string): Align[] {
  return splitRow(line).map((cell) => {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    if (left) return "left";
    return null;
  });
}

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: { text: string; level: number }[] } | null = null;
  let code: { lines: string[]; lang: string } | null = null;
  let mathBlock: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: "p", text: paragraph.join(" ") });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push({ kind: "list", ...list });
    list = null;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index]!;
    if (code !== null) {
      if (raw.trim().startsWith("```")) {
        blocks.push({ kind: "code", text: code.lines.join("\n"), lang: code.lang });
        code = null;
      } else code.lines.push(raw);
      continue;
    }
    if (mathBlock !== null) {
      const closing = raw.trim() === "$$" || raw.trim() === "\\]";
      if (closing || raw.trim().endsWith("$$")) {
        if (!closing) mathBlock.push(raw.trim().slice(0, -2));
        blocks.push({ kind: "math", text: mathBlock.join("\n") });
        mathBlock = null;
      } else mathBlock.push(raw);
      continue;
    }
    const line = raw.trimEnd();
    const stripped = line.trim();
    if (stripped.startsWith("```")) {
      flushParagraph();
      flushList();
      code = { lines: [], lang: stripped.slice(3).trim().toLowerCase() };
      continue;
    }
    if (stripped === "$$" || stripped === "\\[") {
      flushParagraph();
      flushList();
      mathBlock = [];
      continue;
    }
    if (stripped.startsWith("$$") && stripped.endsWith("$$") && stripped.length > 4) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "math", text: stripped.slice(2, -2) });
      continue;
    }
    if (stripped.startsWith("\\[") && stripped.endsWith("\\]") && stripped.length > 4) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "math", text: stripped.slice(2, -2) });
      continue;
    }
    if (stripped.startsWith("$$")) {
      flushParagraph();
      flushList();
      mathBlock = [stripped.slice(2)];
      continue;
    }
    if (!stripped) {
      flushParagraph();
      flushList();
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(stripped)) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "rule" });
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(stripped);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "h", level: heading[1]!.length, text: heading[2] ?? "" });
      continue;
    }
    // Tabela: linha com "|" seguida da linha separadora (|---|---|).
    const next = lines[index + 1]?.trim() ?? "";
    if (stripped.includes("|") && TABLE_SEP.test(next) && next.includes("-")) {
      flushParagraph();
      flushList();
      const header = splitRow(stripped);
      const align = alignments(next);
      const rows: string[][] = [];
      let cursor = index + 2;
      while (cursor < lines.length) {
        const candidate = lines[cursor]!.trim();
        if (!candidate || !candidate.includes("|")) break;
        rows.push(splitRow(candidate));
        cursor += 1;
      }
      blocks.push({ kind: "table", header, align, rows });
      index = cursor - 1;
      continue;
    }
    const item = /^([-*•]|\d+[.)])\s+(.*)$/.exec(stripped);
    if (item) {
      flushParagraph();
      const ordered = /^\d/.test(item[1] ?? "");
      const level = Math.floor((line.length - line.trimStart().length) / 2);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push({ text: item[2] ?? "", level });
      continue;
    }
    if (stripped.startsWith("> ")) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "quote", text: stripped.slice(2) });
      continue;
    }
    if (list && line.startsWith("  ")) {
      // Continuação de um item (linha recuada sem marcador).
      const last = list.items[list.items.length - 1];
      if (last) last.text += ` ${stripped}`;
      continue;
    }
    flushList();
    paragraph.push(stripped);
  }
  if (code !== null) blocks.push({ kind: "code", text: code.lines.join("\n"), lang: code.lang });
  if (mathBlock !== null) blocks.push({ kind: "math", text: mathBlock.join("\n") });
  flushParagraph();
  flushList();
  return blocks;
}
