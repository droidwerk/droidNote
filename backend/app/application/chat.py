from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.application.prompts import chat_grounded_rules, chat_style_rules, chat_system
from app.application.sessions import _fts_query
from app.application.summarize import voice_label
from app.core.i18n import ui_message
from app.domain.models import Chat, ChatCitation, ChatImage, ChatMessage, Session, TranscriptSegment
from app.domain.ports import LlmPort
from app.infrastructure.persistence.sqlite import SqliteStore, new_id

MAX_CONTEXT_CHARS = 12_000
MAX_DOCUMENT_CHARS = 7_000
MAX_DOCUMENT_EXCERPT = 900
LIVE_TAIL_SEGMENTS = 60
MAX_EXCERPT = 420
HISTORY_TURNS = 12
# Todo trecho numerado no contexto vira citação (a tela mostra primeiro os citados na resposta).
MAX_CITATIONS = 64
# Escopo amplo ("todas as aulas do professor X"): quantas notas entram inteiras.
SCOPE_NOTE_SESSIONS = 8
SCOPE_NOTE_CHARS = 700
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 4 * 1024 * 1024
STYLES = ("normal", "fast", "study", "solve")
# Modo rápido: menos contexto = primeira palavra mais cedo num modelo local.
FAST_CONTEXT_CHARS = 4_500
FAST_DOCUMENT_CHARS = 2_500


class SeriesMemory(Protocol):
    async def chat_context(self, session_id: str) -> str: ...


@dataclass(frozen=True)
class ChatScope:
    """Quais gravações a pergunta enxerga. Tudo vazio = automático (busca em todas)."""

    days: int | None = None
    person_id: str | None = None
    tag_id: str | None = None
    session_ids: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return bool(self.days or self.person_id or self.tag_id or self.session_ids)


@dataclass(frozen=True)
class ChatImageIn:
    name: str
    mime: str
    data: bytes


@dataclass
class _Context:
    """Blocos de cabeçalho (catálogo, notas) e trechos numerados que viram citações."""

    headers: list[str] = field(default_factory=list)
    excerpts: list[tuple[ChatCitation, str]] = field(default_factory=list)


class ChatService:
    def __init__(self, llm: LlmPort, store: SqliteStore, memory: SeriesMemory | None = None) -> None:
        self._llm = llm
        self._store = store
        self._memory = memory

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
        document_ids: Sequence[str] | None = None,
        on_token: Callable[[str], None] | None = None,
        ui_language: str | None = None,
        style: str = "normal",
        scope: ChatScope | None = None,
        images: Sequence[ChatImageIn] | None = None,
        grounded: bool = False,
        solve_target: str = "generic",
    ) -> tuple[Chat, ChatMessage, list[ChatCitation]]:
        cleaned = message.strip()
        if not cleaned:
            raise ValueError(ui_message(ui_language, "chat_empty_question"))
        images = list(images or [])[:MAX_IMAGES]
        if images:
            for item in images:
                if len(item.data) > MAX_IMAGE_BYTES:
                    raise ValueError(ui_message(ui_language, "chat_image_too_large"))
            checker = getattr(self._llm, "supports_images", None)
            if callable(checker) and not await checker():
                raise ValueError(ui_message(ui_language, "chat_no_vision"))
        now = datetime.now(tz=UTC)
        chat = await self._ensure_chat(chat_id, session_id, cleaned, now, ui_language)
        try:
            return await self._answer(
                chat,
                cleaned,
                now,
                session_id,
                segment_ids,
                document_ids,
                on_token,
                ui_language,
                style if style in STYLES else "normal",
                scope or ChatScope(),
                images,
                grounded,
                solve_target,
            )
        except BaseException:
            if not chat_id:
                # Conversa nova que falhou (ex.: motor desligado): a tela não recebe o id dela,
                # então os anexos voltam a ficar livres para a próxima tentativa e ela some.
                detach = getattr(self._store, "detach_documents", None)
                if callable(detach):
                    await detach(chat.id)
                await self._store.delete_chat(chat.id)
            raise

    async def _answer(
        self,
        chat: Chat,
        cleaned: str,
        now: datetime,
        session_id: str | None,
        segment_ids: Sequence[str] | None,
        document_ids: Sequence[str] | None,
        on_token: Callable[[str], None] | None,
        ui_language: str | None,
        style: str,
        scope: ChatScope,
        images: list[ChatImageIn],
        grounded: bool,
        solve_target: str,
    ) -> tuple[Chat, ChatMessage, list[ChatCitation]]:
        attach = getattr(self._store, "attach_documents", None)
        if document_ids and callable(attach):
            await attach(chat.id, list(document_ids))
        focus = session_id or chat.focus_session_id
        fast = style == "fast"
        docs = await self._retrieve_documents(
            cleaned, chat.id, focus, limit=FAST_DOCUMENT_CHARS if fast else MAX_DOCUMENT_CHARS
        )
        talk = await self._retrieve(
            cleaned,
            session_id=focus,
            segment_ids=segment_ids or [],
            scope=scope,
            limit=FAST_CONTEXT_CHARS if fast else MAX_CONTEXT_CHARS,
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
        if images:
            saver = getattr(self._store, "save_chat_images", None)
            if callable(saver):
                await saver(
                    [
                        (
                            ChatImage(
                                id=new_id(),
                                message_id=user.id,
                                chat_id=chat.id,
                                name=item.name[:160],
                                mime=item.mime,
                                size=len(item.data),
                            ),
                            item.data,
                        )
                        for item in images
                    ]
                )
        # Trechos numerados: o modelo cita [n] e a tela liga o número à fonte.
        pairs = (docs.excerpts + talk.excerpts)[:MAX_CITATIONS]
        numbered = [f"[{index}] {text}" for index, (_citation, text) in enumerate(pairs, start=1)]
        context = "\n\n".join(docs.headers + talk.headers + numbered)
        citations = [citation for citation, _text in pairs]
        prompt = _build_prompt(cleaned, context, history[-HISTORY_TURNS:], images=len(images))
        system = chat_system(ui_language) + chat_style_rules(style, solve_target) + chat_grounded_rules(grounded)
        # Só manda `images` quando há imagem: motores antigos não conhecem o argumento.
        extra: dict[str, object] = {"images": [item.data for item in images]} if images else {}
        if on_token:
            reply_text = await self._llm.generate_text_stream(prompt, on_token, system=system, **extra)
        else:
            reply_text = await self._llm.generate_text(prompt, system=system, **extra)
        assistant = ChatMessage(
            id=new_id(),
            chat_id=chat.id,
            role="assistant",
            content=(reply_text or "").strip() or ui_message(ui_language, "chat_no_reply"),
            created_at=datetime.now(tz=UTC),
            citations=citations,
            style=style,
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

    async def _retrieve_documents(
        self, query: str, chat_id: str, session_id: str | None = None, *, limit: int = MAX_DOCUMENT_CHARS
    ) -> _Context:
        """Trechos dos documentos anexados ao chat e do material da reunião em foco: os que casam com a
        pergunta e, se faltar, o começo de cada um."""
        out = _Context()
        lister = getattr(self._store, "list_documents", None)
        if not callable(lister):
            return out
        documents = list(await lister(chat_id=chat_id))
        if session_id:
            seen_ids = {item.id for item in documents}
            documents += [item for item in await lister(session_id=session_id) if item.id not in seen_ids]
        if not documents:
            return out
        names = {item.id: item.name for item in documents}
        ids = list(names)
        chunks = await self._store.search_document_chunks(ids, _fts_query(query), limit=10)
        seen = {(chunk.document_id, chunk.ord) for chunk in chunks}
        per_doc = max(2, 8 // len(ids))
        for document_id in ids:
            for chunk in await self._store.first_document_chunks(document_id, per_doc):
                if (chunk.document_id, chunk.ord) not in seen:
                    seen.add((chunk.document_id, chunk.ord))
                    chunks.append(chunk)
        listing = "Attached documents: " + ", ".join(names[item] for item in ids)
        out.headers.append(listing)
        used = len(listing)
        for chunk in chunks:
            excerpt = chunk.text.strip()
            if len(excerpt) > MAX_DOCUMENT_EXCERPT:
                excerpt = excerpt[: MAX_DOCUMENT_EXCERPT - 1] + "…"
            where = f" · p. {chunk.page}" if chunk.page else ""
            line = f"[document] {names[chunk.document_id]}{where}\n{excerpt}"
            if used + len(line) > limit or len(out.excerpts) >= 6:
                break
            used += len(line)
            out.excerpts.append(
                (
                    ChatCitation(
                        session_id="",
                        session_title="",
                        excerpt=excerpt[:MAX_EXCERPT],
                        document_id=chunk.document_id,
                        document_name=names[chunk.document_id],
                        page=chunk.page,
                    ),
                    line,
                )
            )
        return out

    async def _scope_sessions(self, scope: ChatScope, sessions: list[Session]) -> list[Session] | None:
        """Gravações dentro do escopo pedido; None quando o escopo é automático."""
        if not scope.active:
            return None
        allowed: set[str] | None = None

        def narrow(ids: Sequence[str]) -> None:
            nonlocal allowed
            allowed = set(ids) if allowed is None else allowed & set(ids)

        if scope.session_ids:
            narrow(scope.session_ids)
        if scope.person_id:
            narrow(await self._store.list_session_ids_for_person(scope.person_id))
        if scope.tag_id:
            narrow(await self._store.list_session_ids_for_tag(scope.tag_id))
        picked = [item for item in sessions if allowed is None or item.id in allowed]
        if scope.days:
            since = datetime.now(tz=UTC) - timedelta(days=int(scope.days))
            picked = [item for item in picked if item.started_at >= since]
        return picked

    async def _retrieve(
        self,
        query: str,
        *,
        session_id: str | None,
        segment_ids: Sequence[str],
        scope: ChatScope,
        limit: int = MAX_CONTEXT_CHARS,
    ) -> _Context:
        out = _Context()
        people = {item.id: item.name for item in await self._store.list_people()}
        sessions = await self._store.list_sessions()
        titles = {item.id: item.title for item in sessions}
        scoped = await self._scope_sessions(scope, sessions)
        scoped_ids = {item.id for item in scoped} if scoped is not None else None
        picked: list[tuple[TranscriptSegment, str]] = []
        seen: set[str] = set()

        def add(segment: TranscriptSegment, reason: str) -> None:
            if segment.id in seen:
                return
            if scoped_ids is not None and segment.session_id not in scoped_ids and reason != "selected excerpt":
                return
            seen.add(segment.id)
            picked.append((segment, reason))

        for segment in await self._store.get_segments_by_ids(list(segment_ids)):
            add(segment, "selected excerpt")
        focused: list[TranscriptSegment] = []
        live = False
        if session_id:
            focused = await self._store.list_segments(session_id)
            live = any(item.id == session_id and item.status == "recording" for item in sessions)
            if live:
                # Reunião em andamento: "o que eu perdi?" pede o fim da conversa, não o começo,
                # e ela vem antes das outras sessões para não ficar sem espaço no contexto.
                focused = focused[-LIVE_TAIL_SEGMENTS:]
                for segment in focused:
                    add(segment, "live meeting")
        hits = await self._store.search(_fts_query(query))
        for segment in hits[:24]:
            add(segment, "search")
        if not live:
            for segment in focused:
                add(segment, "focused lecture")

        catalog = _session_catalog(scoped if scoped is not None else sessions, scoped is not None)
        used = 0
        if catalog:
            out.headers.append(catalog)
            used += len(catalog)
        if session_id:
            summary = await self._store.get_summary(session_id)
            if summary and (summary.overview or summary.notes_markdown):
                note = (summary.notes_markdown or summary.overview)[:1_800]
                block = f"Note of the focused lecture ({titles.get(session_id, session_id)}):\n{note}"
                out.headers.append(block)
                used += len(block)
            if self._memory is not None:
                # "O que mudou desde a última reunião?" precisa das reuniões anteriores da série.
                try:
                    thread = await self._memory.chat_context(session_id)
                except Exception:
                    thread = ""
                if thread:
                    out.headers.append(thread[:2_400])
                    used += len(thread[:2_400])
        if scoped is not None:
            # Escopo amplo: a nota de cada gravação entra resumida, para comparar e somar.
            for item in scoped[:SCOPE_NOTE_SESSIONS]:
                if item.id == session_id:
                    continue
                summary = await self._store.get_summary(item.id)
                text = (summary.overview or summary.notes_markdown) if summary else ""
                if not text:
                    continue
                block = f"Note of {item.title} ({item.started_at.astimezone().strftime('%Y-%m-%d')}):\n{text[:SCOPE_NOTE_CHARS]}"
                out.headers.append(block)
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
            if not speaker and segment.speaker_cluster:
                speaker = voice_label(segment.speaker_cluster, segment.language)
            who = f" {speaker}" if speaker else ""
            line = f"[{reason}] {title} · {stamp}{who}\n{excerpt}"
            if used + len(line) > limit:
                break
            used += len(line)
            out.excerpts.append(
                (
                    ChatCitation(
                        session_id=segment.session_id,
                        session_title=title,
                        segment_id=segment.id,
                        start_ms=segment.start_ms,
                        excerpt=excerpt,
                    ),
                    line,
                )
            )
        return out


def _session_catalog(sessions: list[Session], scoped: bool = False) -> str:
    if not sessions:
        return "No lectures in the requested scope." if scoped else "No lectures captured yet."
    lines = ["Lectures in scope for this question:" if scoped else "Lectures in the notebook:"]
    for item in sessions[:20]:
        when = item.started_at.astimezone().strftime("%Y-%m-%d")
        mode = {"lecture": "lecture", "meeting": "meeting", "dictation": "dictation"}.get(
            item.capture_mode, item.capture_mode
        )
        lines.append(f"- {item.title} ({mode}, {when})")
    return "\n".join(lines)


def _build_prompt(message: str, context: str, history: list[ChatMessage], *, images: int = 0) -> str:
    parts = ["Context from attached documents, lectures and transcripts:", context or "(no excerpt retrieved)", ""]
    if history:
        parts.append("Conversation so far:")
        for item in history:
            label = "User" if item.role == "user" else "Assistant"
            parts.append(f"{label}: {item.content}")
        parts.append("")
    if images:
        parts.append(
            f"The user attached {images} image(s) (a photo of the board or a slide). Read what is written or drawn in them and use it as part of the question."
        )
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
