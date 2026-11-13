"""Chamadas escolhidas no chat limitam as citações a elas."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.application.chat import ChatScope, ChatService
from app.domain.models import Session, TranscriptSegment
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from app.schemas.api import ChatScopeIn


class _Llm:
    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        return "ok"

    async def generate_text_stream(self, prompt: str, on_token, *, system: str | None = None) -> str:
        return "ok"


async def _setup(tmp_path) -> tuple[SqliteStore, list[str]]:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    return await _setup_into(store)


async def _setup_into(store: SqliteStore) -> tuple[SqliteStore, list[str]]:
    ids = []
    for name in ("Alfa", "Beta", "Gama"):
        session = Session(id=new_id(), title=name, started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
        await store.create_session(session)
        await store.add_segment(
            TranscriptSegment(
                id=new_id(), session_id=session.id, start_ms=0, end_ms=1_000, text=f"orcamento discutido na {name}"
            )
        )
        ids.append(session.id)
    return store, ids


def _sessions(citations) -> set[str]:
    return {item.session_id for item in citations if item.session_id}


async def test_one_selected_session_cites_only_it(tmp_path) -> None:
    store, (alfa, _beta, _gama) = await _setup(tmp_path)
    chat, _, citations = await ChatService(_Llm(), store).ask("orcamento", session_id=alfa)
    assert _sessions(citations) == {alfa}
    # Turno seguinte com o mesmo pedido: continua só nela.
    _, _, later = await ChatService(_Llm(), store).ask("orcamento", chat_id=chat.id, session_id=alfa)
    assert _sessions(later) == {alfa}


async def test_saved_focus_does_not_narrow_request_without_scope(tmp_path) -> None:
    store, ids = await _setup(tmp_path)
    chat, _, _ = await ChatService(_Llm(), store).ask("orcamento", session_id=ids[0])
    assert chat.focus_session_id == ids[0]
    # Sem chips e sem session_id no pedido: todas as conversas, mesmo com foco salvo.
    _, _, later = await ChatService(_Llm(), store).ask("orcamento", chat_id=chat.id)
    assert _sessions(later) == set(ids)


async def test_scope_chips_persist_and_return(client, app) -> None:
    from tests.conftest import auth

    store, ids = await _setup_into(app.state.container.store)
    chips = ids[:2]
    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "orcamento", "scope": {"session_ids": chips}}
    ) as response:
        lines = [line async for line in response.aiter_lines() if line]
    first = json.loads(lines[0].removeprefix("data: "))
    chat_id = first["chat_id"]
    detail = (await client.get(f"/chat/{chat_id}", headers=auth())).json()
    assert detail["chat"]["scope_session_ids"] == chips
    # Pergunta seguinte sem escopo: os chips gravados viram lista vazia.
    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "orcamento", "chat_id": chat_id, "scope": None}
    ) as response:
        [line async for line in response.aiter_lines()]
    detail = (await client.get(f"/chat/{chat_id}", headers=auth())).json()
    assert detail["chat"]["scope_session_ids"] == []


async def test_one_selected_session_via_scope(tmp_path) -> None:
    store, (_alfa, beta, _gama) = await _setup(tmp_path)
    _, _, citations = await ChatService(_Llm(), store).ask("orcamento", scope=ChatScope(session_ids=(beta,)))
    assert _sessions(citations) == {beta}


async def test_two_selected_sessions_cite_only_them(tmp_path) -> None:
    store, (alfa, beta, _gama) = await _setup(tmp_path)
    _, _, citations = await ChatService(_Llm(), store).ask("orcamento", scope=ChatScope(session_ids=(alfa, beta)))
    assert _sessions(citations) == {alfa, beta}


async def test_no_selection_searches_all(tmp_path) -> None:
    store, ids = await _setup(tmp_path)
    _, _, citations = await ChatService(_Llm(), store).ask("orcamento")
    assert _sessions(citations) == set(ids)


def test_scope_caps_selection_at_20() -> None:
    ChatScopeIn(session_ids=[str(i) for i in range(20)])
    with pytest.raises(ValidationError):
        ChatScopeIn(session_ids=[str(i) for i in range(21)])
