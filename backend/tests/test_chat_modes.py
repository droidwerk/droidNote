"""Comandos "/", modo estudo e modo resolver no chat. LLM falso, sem rede."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.application.chat import ChatService
from app.domain.models import Session, Summary, TranscriptSegment
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from app.schemas.api import ChatAskIn

FLASHCARDS_ASK = "Crie flashcards para revisar este conteudo: uma tabela com as colunas Pergunta e Resposta."


class _Llm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system or ""))
        return "ok"

    async def generate_text_stream(self, prompt: str, on_token, *, system: str | None = None) -> str:
        return await self.generate_text(prompt, system=system)

    @property
    def prompt(self) -> str:
        return self.calls[-1][0]

    @property
    def system(self) -> str:
        return self.calls[-1][1]


async def _store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    return store


async def _session(store: SqliteStore, minutes: int, text: str = "o professor explica derivadas e limites") -> str:
    session = Session(id=new_id(), title="Aula", started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
    await store.create_session(session)
    for second in range(0, minutes * 60, 6):
        await store.add_segment(
            TranscriptSegment(
                id=new_id(), session_id=session.id, start_ms=second * 1000, end_ms=second * 1000 + 2_500,
                text=f"{text} parte {second}", source="loopback",
            )
        )
    return session.id


def _spy_search(store: SqliteStore) -> list[str]:
    queries: list[str] = []
    real = store.search

    async def search(fts: str, **kwargs):
        queries.append(fts)
        return await real(fts, **kwargs)

    store.search = search  # type: ignore[method-assign]
    return queries


def _stamps(prompt: str) -> list[int]:
    return [int(m) * 60 + int(s) for m, s in re.findall(r"^\[\d+\] (?:\[[\w ]+\] )?[^\n]*?· (\d\d):(\d\d)", prompt, re.M)]


async def test_command_skips_search_and_covers_whole_lecture(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 60)
    queries = _spy_search(store)
    llm = _Llm()
    _, message, _ = await ChatService(llm, store).ask(FLASHCARDS_ASK, session_id=session_id, command="flashcards")
    assert queries == []  # o texto do comando nunca vira busca
    assert "Reply mode: study" in llm.system and message.style == "study"
    stamps = _stamps(llm.prompt)
    assert stamps and max(stamps) - min(stamps) >= 0.8 * 60 * 60


async def test_unknown_command_is_ignored(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 5)
    queries = _spy_search(store)
    llm = _Llm()
    _, message, _ = await ChatService(llm, store).ask("o que sao derivadas?", session_id=session_id, command="rm -rf")
    assert queries and "derivada*" in queries[0]
    assert message.style == "normal" and "Reply mode" not in llm.system


def test_command_field_is_optional_and_bounded() -> None:
    assert ChatAskIn(message="oi").command is None
    assert ChatAskIn(message="oi", command="exam").command == "exam"
    with pytest.raises(ValidationError):
        ChatAskIn(message="oi", command="x" * 33)


async def test_study_rules_ask_five_cited_questions_with_hidden_answers(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 5)
    llm = _Llm()
    await ChatService(llm, store).ask("me explique limites", session_id=session_id, style="study")
    assert "exactly 5 numbered questions" in llm.system
    assert "a line with only ---" in llm.system


async def test_solve_without_sources_writes_no_plan(tmp_path) -> None:
    store = await _store(tmp_path)  # nenhuma gravação nem documento
    llm = _Llm()
    await ChatService(llm, store).ask("como construo o modulo de lembretes?", style="solve")
    assert "no source" in llm.system
    assert "```prompt" not in llm.system and "**Plan**" not in llm.system


async def test_solve_full_plan_only_on_first_turn_or_when_prompt_is_asked(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 5, "o bug do login aparece ao salvar o formulario")
    llm = _Llm()
    service = ChatService(llm, store)
    chat, _, _ = await service.ask("bug do login", session_id=session_id, style="solve", solve_target="claude")
    assert "**Plan**" in llm.system and "Claude Code" in llm.system

    await service.ask("e no celular tambem acontece?", chat_id=chat.id, session_id=session_id, style="solve")
    assert "follow-up" in llm.system and "**Plan**" not in llm.system

    await service.ask("refaca o prompt do agente", chat_id=chat.id, session_id=session_id, style="solve")
    assert "**Plan**" in llm.system


async def test_solve_no_source_then_pick_conversation_gets_full_plan(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 5, "o bug do login aparece ao salvar o formulario")
    llm = _Llm()
    service = ChatService(llm, store)
    chat, _, _ = await service.ask("como construo o modulo de lembretes?", style="solve")
    assert "no source" in llm.system
    # O aviso "sem fonte" não é plano: escolhida a conversa, vem o plano completo.
    await service.ask("bug do login", chat_id=chat.id, session_id=session_id, style="solve")
    assert "**Plan**" in llm.system


async def test_summary_command_without_focus_uses_latest_conversation(tmp_path) -> None:
    store = await _store(tmp_path)
    await _session(store, 5)
    llm = _Llm()
    _, _, citations = await ChatService(llm, store).ask("Resuma esta conversa.", command="summary")
    assert citations


async def test_solve_with_note_but_purged_transcript_is_not_no_source(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 1, "o bug do login aparece ao salvar o formulario")
    await store.save_summary(
        Summary(
            id=new_id(), session_id=session_id, highlights=[], decisions=[], action_items=[],
            raw_text="{}", created_at=datetime.now(tz=UTC), overview="Bug do login ao salvar o formulario.",
        )
    )
    await store.purge_transcript(session_id)
    llm = _Llm()
    await ChatService(llm, store).ask("bug do login", session_id=session_id, style="solve")
    assert "no source" not in llm.system and "**Plan**" in llm.system


async def test_solve_outline_reminder_is_last_in_user_turn_only_on_full_plan(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 5, "o bug do login aparece ao salvar o formulario")
    llm = _Llm()
    service = ChatService(llm, store)
    chat, _, _ = await service.ask("bug do login", session_id=session_id, style="solve")
    # Depois dos trechos e da pergunta: o modelo local pequeno ignorava o esqueleto só no system.
    assert llm.prompt.rstrip().endswith("Start your reply with the heading of part 1.")
    assert llm.prompt.index("User question:") < llm.prompt.index("Reply format (required)")
    assert "[search]" not in llm.prompt and "[focused lecture]" not in llm.prompt  # etiqueta interna fora

    await service.ask("e no celular tambem acontece?", chat_id=chat.id, session_id=session_id, style="solve")
    assert "Reply format" not in llm.prompt  # follow-up segue sem esqueleto
    assert llm.prompt.rstrip().endswith("is exactly ```prompt.") and "at most three [n] per bullet" in llm.prompt

    await ChatService(llm, await _store(tmp_path / "vazio")).ask("como resolvo o cache?", style="solve")
    assert "Reply format" not in llm.prompt and '"aula"' in llm.system  # sem fonte: só a regra curta


async def test_flashcards_turn_ends_with_answers_below_rule(tmp_path) -> None:
    store = await _store(tmp_path)
    session_id = await _session(store, 5)
    llm = _Llm()
    await ChatService(llm, store).ask(FLASHCARDS_ASK, session_id=session_id, command="flashcards")
    # Pedido de tabela não leva a resposta para cima do ---.
    assert llm.prompt.rstrip().endswith("with the same numbers.") and "never an answer" in llm.prompt
