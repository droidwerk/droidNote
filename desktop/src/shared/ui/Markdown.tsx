import { Fragment, type ReactNode } from "react";

interface MarkdownProps {
  text: string;
  /** Marca de tempo (12:40) vira um elemento clicável; sem isso fica como texto. */
  renderStamp?: (stamp: string) => ReactNode;
  className?: string;
}

type Block =
  | { kind: "p"; text: string }
  | { kind: "h"; level: number; text: string }
  | { kind: "code"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "list"; ordered: boolean; items: { text: string; level: number }[] };

const STAMP = /\b(\d{1,2}:\d{2}(?::\d{2})?)\b/g;
const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

/** Markdown das respostas da IA renderizado sem HTML cru: títulos, listas, negrito, código e marcas de tempo. */
export function Markdown({ text, renderStamp, className }: MarkdownProps) {
  const blocks = parseBlocks(text);
  return (
    <div className={className ? `md ${className}` : "md"}>
      {blocks.map((block, index) => (
        <Fragment key={index}>{renderBlock(block, renderStamp)}</Fragment>
      ))}
    </div>
  );
}

function renderBlock(block: Block, renderStamp?: (stamp: string) => ReactNode): ReactNode {
  if (block.kind === "h") {
    const level = Math.min(Math.max(block.level, 1), 4);
    const content = inline(block.text, renderStamp);
    if (level === 1) return <h3>{content}</h3>;
    if (level === 2) return <h4>{content}</h4>;
    return <h5>{content}</h5>;
  }
  if (block.kind === "code") {
    return (
      <pre>
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.kind === "quote") return <blockquote>{inline(block.text, renderStamp)}</blockquote>;
  if (block.kind === "list") return renderList(block.items, block.ordered, renderStamp);
  return <p>{inline(block.text, renderStamp)}</p>;
}

function renderList(items: { text: string; level: number }[], ordered: boolean, renderStamp?: (stamp: string) => ReactNode): ReactNode {
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
      children.push(<li key={index}>{inline(item.text, renderStamp)}</li>);
      index += 1;
    }
    const List = ordered ? "ol" : "ul";
    return [<List key={`l${start}`}>{children}</List>, index];
  };
  return build(0, items[0]?.level ?? 0)[0];
}

function inline(text: string, renderStamp?: (stamp: string) => ReactNode): ReactNode[] {
  const out: ReactNode[] = [];
  text.split(INLINE).forEach((piece, index) => {
    if (!piece) return;
    if (piece.startsWith("**") && piece.endsWith("**")) out.push(<strong key={index}>{stamps(piece.slice(2, -2), renderStamp)}</strong>);
    else if (piece.startsWith("__") && piece.endsWith("__")) out.push(<strong key={index}>{stamps(piece.slice(2, -2), renderStamp)}</strong>);
    else if (piece.startsWith("`") && piece.endsWith("`")) out.push(<code key={index}>{stampsInCode(piece.slice(1, -1), renderStamp)}</code>);
    else if ((piece.startsWith("*") && piece.endsWith("*")) || (piece.startsWith("_") && piece.endsWith("_")))
      out.push(<em key={index}>{stamps(piece.slice(1, -1), renderStamp)}</em>);
    else out.push(<Fragment key={index}>{stamps(piece, renderStamp)}</Fragment>);
  });
  return out;
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

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: { text: string; level: number }[] } | null = null;
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: "p", text: paragraph.join(" ") });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push({ kind: "list", ...list });
    list = null;
  };

  for (const raw of lines) {
    if (code !== null) {
      if (raw.trim().startsWith("```")) {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      } else code.push(raw);
      continue;
    }
    const line = raw.trimEnd();
    const stripped = line.trim();
    if (stripped.startsWith("```")) {
      flushParagraph();
      flushList();
      code = [];
      continue;
    }
    if (!stripped) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(stripped);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "h", level: heading[1]!.length, text: heading[2] ?? "" });
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
  if (code !== null) blocks.push({ kind: "code", text: code.join("\n") });
  flushParagraph();
  flushList();
  return blocks;
}
