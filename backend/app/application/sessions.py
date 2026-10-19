from __future__ import annotations

import re
from dataclasses import replace

from app.domain.models import Session, Summary, TranscriptSegment
from app.domain.ports import SessionRepository


class SessionService:
    def __init__(self, store: SessionRepository) -> None:
        self._store = store

    async def list_sessions(self) -> list[Session]:
        return await self._store.list_sessions()

    async def get(self, session_id: str) -> Session:
        session = await self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    async def rename(self, session_id: str, title: str) -> Session:
        session = await self.get(session_id)
        updated = replace(session, title=title.strip())
        await self._store.update_session(updated)
        return updated

    async def delete(self, session_id: str) -> None:
        await self.get(session_id)
        await self._store.delete_session(session_id)

    async def segments(self, session_id: str) -> list[TranscriptSegment]:
        await self.get(session_id)
        return await self._store.list_segments(session_id)

    async def search(self, query: str, session_id: str | None = None) -> list[TranscriptSegment]:
        cleaned = query.strip()
        if not cleaned:
            return []
        return await self._store.search(_fts_query(cleaned), session_id=session_id)

    async def save_note(self, session_id: str, notes_markdown: str) -> Summary:
        await self.get(session_id)
        summary = await self._store.get_summary(session_id)
        if summary is None:
            raise KeyError(session_id)
        updated = replace(summary, notes_markdown=notes_markdown)
        await self._store.save_summary(updated)
        return updated

    async def export_markdown(self, session_id: str, locale: str | None = None) -> str:
        from app.application.summarize import voice_label
        from app.core.i18n import ui_message

        session = await self.get(session_id)
        segments = await self._store.list_segments(session_id)
        summary = await self._store.get_summary(session_id)
        lines = [
            f"# {session.title}",
            "",
            f"- {ui_message(locale, 'export_start')}: {session.started_at.isoformat()}",
        ]
        if session.ended_at:
            lines.append(f"- {ui_message(locale, 'export_end')}: {session.ended_at.isoformat()}")
        if session.language:
            lines.append(f"- {ui_message(locale, 'export_language')}: {session.language}")
        lines.extend(["", f"## {ui_message(locale, 'export_transcript')}", ""])
        people = {item.id: item.name for item in await self._store.list_people()}
        for segment in segments:
            stamp = _fmt_ms(segment.start_ms)
            lang = f" ({segment.language})" if segment.language else ""
            speaker = ""
            if segment.speaker_id and segment.speaker_id in people:
                speaker = f" {people[segment.speaker_id]}"
            elif segment.speaker_cluster:
                speaker = f" {voice_label(segment.speaker_cluster, segment.language or session.language)}"
            lines.append(f"- [{stamp}]{speaker}{lang} {segment.text}")
        if summary:
            lines.extend(
                ["", f"## {ui_message(locale, 'export_summary')}", "", f"### {ui_message(locale, 'export_highlights')}"]
            )
            lines.extend([f"- {item}" for item in summary.highlights] or ["- —"])
            lines.extend(["", f"### {ui_message(locale, 'export_decisions')}"])
            lines.extend([f"- {item}" for item in summary.decisions] or ["- —"])
            lines.extend(["", f"### {ui_message(locale, 'export_actions')}"])
            if summary.action_items:
                for item in summary.action_items:
                    owner = f" ({item.owner})" if item.owner else ""
                    lines.append(f"- {item.text}{owner}")
            else:
                lines.append("- —")
        return "\n".join(lines) + "\n"


def _fts_query(raw: str) -> str:
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", raw)
    if not tokens:
        return raw.replace('"', "")
    return " OR ".join(tokens[:16])


def _fmt_ms(value: int) -> str:
    seconds = max(value, 0) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
