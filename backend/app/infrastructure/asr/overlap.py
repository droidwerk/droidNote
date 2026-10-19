from __future__ import annotations


def drop_covered_words(
    words: list[tuple[float, float, str]],
    start_ms: int,
    covered_until_ms: int | None,
) -> list[tuple[float, float, str]]:
    """Tira palavras que já cabem na janela anterior (a fronteira de 1 s)."""
    if covered_until_ms is None or not words:
        return words
    kept: list[tuple[float, float, str]] = []
    for begin, end, text in words:
        if start_ms + end * 1000 <= covered_until_ms:
            continue
        kept.append((begin, end, text))
    return kept


def strip_overlap(previous: str, current: str, *, max_tokens: int = 12) -> str:
    prev = (previous or "").strip()
    curr = (current or "").strip()
    if not prev or not curr:
        return curr
    if curr == prev:
        return curr
    if curr.startswith(prev):
        return curr[len(prev) :].strip()
    prev_tokens = prev.split()
    curr_tokens = curr.split()
    if prev_tokens == curr_tokens:
        return curr
    limit = min(len(prev_tokens), len(curr_tokens), max_tokens)
    for count in range(limit, 1, -1):
        if prev_tokens[-count:] == curr_tokens[:count]:
            return " ".join(curr_tokens[count:]).strip()
    return curr
