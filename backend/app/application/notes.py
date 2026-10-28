"""IA sobre as anotações: transforma uma linha curta em um registro completo.

A pessoa anota "preço caro" no meio da reunião; a IA olha o que foi dito em
volta daquele momento e devolve 2 a 4 frases com quem disse o quê. É uma
sugestão: a interface mostra e a pessoa decide se substitui ou acrescenta.
"""

from __future__ import annotations

from app.application.summarize import voice_label
from app.core.i18n import normalize_ui_language
from app.domain.models import UserNote
from app.domain.ports import LlmPort
from app.infrastructure.persistence.sqlite import SqliteStore

WINDOW_BEFORE_MS = 90_000
WINDOW_AFTER_MS = 45_000
MAX_CHARS = 6_000

LANGUAGE = {
    "pt": "Brazilian Portuguese",
    "en": "English",
    "es": "Spanish",
    "it": "Italian",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
}

SYSTEM = (
    "You turn a short note a person typed during a conversation into a clear, complete record. "
    "Use only what the transcript excerpt says. Never invent names, numbers or decisions. "
    "Reply with 2 to 4 plain sentences, no headings, no bullet points, no preamble. "
    "Write in {language}."
)


async def expand_note(llm: LlmPort, store: SqliteStore, note: UserNote, ui_language: str | None) -> str:
    segments = await store.list_segments(note.session_id)
    people = {item.id: item.name for item in await store.list_people()}
    lo, hi = note.at_ms - WINDOW_BEFORE_MS, note.at_ms + WINDOW_AFTER_MS
    lines: list[str] = []
    used = 0
    for segment in segments:
        if segment.end_ms < lo or segment.start_ms > hi:
            continue
        who = people.get(segment.speaker_id or "") or (
            voice_label(segment.speaker_cluster, segment.language) if segment.speaker_cluster else ""
        )
        line = f"[{_clock(segment.start_ms)}] {who + ': ' if who else ''}{segment.text.strip()}"
        if used + len(line) > MAX_CHARS:
            break
        lines.append(line)
        used += len(line)
    kind = f"Marked as: {note.kind}.\n" if note.kind else ""
    prompt = (
        f"Note typed at {_clock(note.at_ms)}: {note.text}\n{kind}\n"
        "Transcript around that moment:\n"
        + ("\n".join(lines) if lines else "(no speech recorded around this moment)")
        + "\n\nRewrite the note as a complete record of what happened at that moment."
    )
    language = LANGUAGE[normalize_ui_language(ui_language)]
    text = await llm.generate_text(prompt, system=SYSTEM.format(language=language))
    return (text or "").strip()


def _clock(ms: int) -> str:
    seconds = max(ms, 0) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}" if hours else f"{minutes:02d}:{sec:02d}"
