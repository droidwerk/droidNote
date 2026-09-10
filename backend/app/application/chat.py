from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime

from app.application.prompts import chat_system
from app.application.sessions import _fts_query
from app.core.i18n import ui_message
from app.domain.models import Chat, ChatCitation, ChatMessage, Session, TranscriptSegment
from app.domain.ports import LlmPort
from app.infrastructure.persistence.sqlite import SqliteStore, new_id

MAX_CONTEXT_CHARS = 12_000
MAX_EXCERPT = 420
HISTORY_TURNS = 12


class ChatService:
    def __init__(self, llm: LlmPort, store: SqliteStore) -> None:
        self._llm = llm
        self._store = store

    async def list_chats(self) -> list[Chat]:
        return await self._store.list_chats()

    async def get(self, chat_id: str) -> tuple[Chat, list[ChatMessage]]:
        chat = await self._store.get_chat(chat_id)
        if chat is None:
            raise KeyError(chat_id)
        return chat, await self._store.list_chat_messages(chat_id)

    async def delete(self, chat_id: str) -> None:
        await self._store.delete_chat(chat_id)

    async def ask(
        self,
        message: str,
        *,
        chat_id: str | None = None,
        session_id: str | None = None,
        segment_ids: Sequence[str] | None = None,
        on_token: Callable[[str], None] | None = None,
        ui_language: str | None = None,
    ) -> tuple[Chat, ChatMessage, list[ChatCitation]]:
        cleaned = message.strip()
        if not cleaned:
            raise ValueError(ui_message(ui_language, "chat_empty_question"))
        now = datetime.now(tz=UTC)
        chat = await self._ensure_chat(chat_id, session_id, cleaned, now, ui_language)
        citations, context = await self._retrieve(
            cleaned,
            session_id=session_id or chat.focus_session_id,
            segment_ids=segment_ids or [],
        )
        history = await self._store.list_chat_messages(chat.id)
        user = ChatMessage(
            id=new_id(),
            chat_id=chat.id,
            role="user",
            content=cleaned,
            created_at=now,
        )
        await self._store.add_chat_message(user)
        prompt = _build_prompt(cleaned, context, history[-HISTORY_TURNS:])
        system = chat_system(ui_language)
        if on_token:
            reply_text = await self._llm.generate_text_stream(prompt, on_token, system=system)
        else:
            reply_text = await self._llm.generate_text(prompt, system=system)
        assistant = ChatMessage(
            id=new_id(),
            chat_id=chat.id,
            role="assistant",
            content=(reply_text or "").strip() or ui_message(ui_language, "chat_no_reply"),
            created_at=datetime.now(tz=UTC),
            citations=citations,
        )
        await self._store.add_chat_message(assistant)
        chat = replace(chat, updated_at=assistant.created_at)
        await self._store.save_chat(chat)
        return chat, assistant, citations

    async def _ensure_chat(
        self,
        chat_id: str | None,
        session_id: str | None,
        message: str,
        now: datetime,
        ui_language: str | None = None,
    ) -> Chat:
        if chat_id:
            existing = await self._store.get_chat(chat_id)
            if existing is None:
                raise KeyError(chat_id)
            return existing
        title = message.strip().split("\n", 1)[0][:72]
        chat = Chat(
            id=new_id(),
            title=title or ui_message(ui_language, "chat_untitled"),
            created_at=now,
            updated_at=now,
            focus_session_id=session_id,
        )
        await self._store.save_chat(chat)
        return chat

    async def _retrieve(
        self,
        query: str,
        *,
        session_id: str | None,
        segment_ids: Sequence[str],
    ) -> tuple[list[ChatCitation], str]:
        people = {item.id: item.name for item in await self._store.list_people()}
        sessions = await self._store.list_sessions()
        titles = {item.id: item.title for item in sessions}
        picked: list[tuple[TranscriptSegment, str]] = []
        seen: set[str] = set()

        def add(segment: TranscriptSegment, reason: str) -> None:
            if segment.id in seen:
                return
            seen.add(segment.id)
            picked.append((segment, reason))

        for segment in await self._store.get_segments_by_ids(list(segment_ids)):
            add(segment, "selected excerpt")
        hits = await self._store.search(_fts_query(query))
        for segment in hits[:24]:
            add(segment, "search")
        if session_id:
            for segment in await self._store.list_segments(session_id):
                add(segment, "focused lecture")

        catalog = _session_catalog(sessions)
        blocks: list[str] = []
        citations: list[ChatCitation] = []
        used = 0
        if catalog:
            blocks.append(catalog)
            used += len(catalog)
        if session_id:
            summary = await self._store.get_summary(session_id)
            if summary and (summary.overview or summary.notes_markdown):
                note = (summary.notes_markdown or summary.overview)[:1_800]
                block = f"Note of the focused lecture ({titles.get(session_id, session_id)}):\n{note}"
                blocks.append(block)
                used += len(block)

        for segment, reason in picked:
            excerpt = segment.text.strip()
            if not excerpt:
                continue
            if len(excerpt) > MAX_EXCERPT:
                excerpt = excerpt[: MAX_EXCERPT - 1] + "…"
            title = titles.get(segment.session_id, "Lecture")
            stamp = _fmt_ms(segment.start_ms)
            speaker = people.get(segment.speaker_id or "", "")
            who = f" {speaker}" if speaker else ""
            line = f"[{reason}] {title} · {stamp}{who}\n{excerpt}"
            if used + len(line) > MAX_CONTEXT_CHARS:
                break
            blocks.append(line)
            used += len(line)
            citations.append(
                ChatCitation(
                    session_id=segment.session_id,
                    session_title=title,
                    segment_id=segment.id,
                    start_ms=segment.start_ms,
                    excerpt=excerpt,
                )
            )
        return citations[:12], "\n\n".join(blocks)


def _session_catalog(sessions: list[Session]) -> str:
    if not sessions:
        return "No lectures captured yet."
    lines = ["Lectures in the notebook:"]
    for item in sessions[:20]:
        when = item.started_at.astimezone().strftime("%Y-%m-%d")
        mode = {"lecture": "lecture", "meeting": "meeting", "dictation": "dictation"}.get(
            item.capture_mode, item.capture_mode
        )
        lines.append(f"- {item.title} ({mode}, {when})")
    return "\n".join(lines)


def _build_prompt(message: str, context: str, history: list[ChatMessage]) -> str:
    parts = ["Context from lectures and transcripts:", context or "(no excerpt retrieved)", ""]
    if history:
        parts.append("Conversation so far:")
        for item in history:
            label = "User" if item.role == "user" else "Assistant"
            parts.append(f"{label}: {item.content}")
        parts.append("")
    parts.append(f"User question:\n{message}")
    return "\n".join(parts)


def _fmt_ms(value: int) -> str:
    seconds = max(value, 0) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
