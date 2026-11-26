const RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;

/**
 * Resposta do modo Estudar: o gabarito vem depois da última linha "---" (ou num <details>, que o
 * Markdown do chat não renderiza). Devolve a parte visível e a parte que fica fechada até a pessoa abrir.
 */
export function splitReveal(text: string): { visible: string; hidden: string | null } {
  const details = text.search(/<details\b/i);
  if (details >= 0) {
    const hidden = text
      .slice(details)
      .replace(/<summary\b[^>]*>[\s\S]*?<\/summary>/gi, "")
      .replace(/<\/?details\b[^>]*>/gi, "")
      .trim();
    return hidden ? { visible: text.slice(0, details).trimEnd(), hidden } : { visible: text, hidden: null };
  }
  const lines = text.split("\n");
  let fenced = false;
  let rule = -1;
  lines.forEach((line, index) => {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
    else if (!fenced && RULE.test(line)) rule = index;
  });
  if (rule < 0) return { visible: text, hidden: null };
  const hidden = lines.slice(rule + 1).join("\n").trim();
  // Só gabarito numerado fecha; "---" usado como quebra de seção fica visível.
  if (!/^1[.)]\s/.test(hidden)) return { visible: text, hidden: null };
  return { visible: lines.slice(0, rule).join("\n").trimEnd(), hidden };
}
