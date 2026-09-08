from __future__ import annotations


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
