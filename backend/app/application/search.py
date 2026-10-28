"""Busca além das falas: anotações, atas e tarefas (sem diferenciar acento nem caixa)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.infrastructure.persistence.sqlite import SqliteStore

LIMIT = 8
EXCERPT = 140


@dataclass(frozen=True, slots=True)
class NoteHit:
    id: str
    session_id: str
    at_ms: int
    text: str
    kind: str | None


@dataclass(frozen=True, slots=True)
class SummaryHit:
    session_id: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class TaskHit:
    id: str
    session_id: str | None
    text: str
    done: bool


@dataclass(frozen=True, slots=True)
class ExtraHits:
    notes: list[NoteHit]
    summaries: list[SummaryHit]
    tasks: list[TaskHit]


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


async def search_extras(store: SqliteStore, query: str) -> ExtraHits:
    needle = fold(query.strip())
    if len(needle) < 2:
        return ExtraHits([], [], [])
    notes, summaries = await store.searchable_texts()
    note_hits = [
        NoteHit(id=item[0], session_id=item[1], at_ms=item[2], text=item[3], kind=item[4])
        for item in notes
        if needle in fold(item[3])
    ][:LIMIT]
    summary_hits: list[SummaryHit] = []
    for session_id, markdown in summaries:
        line = _matching_line(markdown, needle)
        if line:
            summary_hits.append(SummaryHit(session_id=session_id, excerpt=line))
        if len(summary_hits) >= LIMIT:
            break
    task_hits = [
        TaskHit(id=item.id, session_id=item.session_id, text=item.text, done=item.done)
        for item in await store.list_tasks()
        if needle in fold(item.text)
    ][:LIMIT]
    return ExtraHits(note_hits, summary_hits, task_hits)


def _matching_line(markdown: str, needle: str) -> str | None:
    """A linha da ata que contém o termo, sem a marcação de markdown, cortada em volta dele."""
    for raw in markdown.splitlines():
        line = re.sub(r"^\s*(#+|[-*]|\d+\.)\s*", "", raw).replace("`", "").replace("**", "").strip()
        folded = fold(line)
        at = folded.find(needle)
        if at < 0:
            continue
        if len(line) <= EXCERPT:
            return line
        start = max(0, at - EXCERPT // 3)
        piece = line[start : start + EXCERPT].strip()
        return ("…" if start else "") + piece + ("…" if start + EXCERPT < len(line) else "")
    return None
