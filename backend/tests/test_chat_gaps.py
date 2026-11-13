"""Renomear conversa, guardar a resposta parcial ao parar e não duplicar a pergunta ao tentar de novo."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.application.chat import ChatService
from app.infrastructure.persistence.sqlite import SqliteStore
from tests.conftest import auth


class _Llm:
    def __init__(self) -> None:
        self.fail = False
        self.hang = False
        self.started = asyncio.Event()

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        return "ok"

    async def generate_text_stream(self, prompt: str, on_token, *, system: str | None = None) -> str:
        if self.fail:
            raise ConnectionError("motor fora")
        on_token("Resposta ")
        on_token("pela metade")
        if self.hang:
            self.started.set()
            await asyncio.Event().wait()
        return "Resposta completa"


async def _store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_rename_chat(client: AsyncClient, app) -> None:
    chat, _, _ = await app.state.container.chat.ask("Pergunta inicial")
    renamed = await client.patch(f"/chat/{chat.id}", headers=auth(), json={"title": "  Novo nome  "})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Novo nome"
    assert renamed.json()["updated_at"] == (await client.get(f"/chat/{chat.id}", headers=auth())).json()["chat"]["updated_at"]
    listed = (await client.get("/chat", headers=auth())).json()
    assert listed[0]["title"] == "Novo nome"

    assert (await client.patch("/chat/nao-existe", headers=auth(), json={"title": "x"})).status_code == 404
    assert (await client.patch(f"/chat/{chat.id}", headers=auth(), json={"title": "   "})).status_code == 422
    assert (await client.patch(f"/chat/{chat.id}", headers=auth(), json={"title": "a" * 121})).status_code == 422
    assert (await client.patch(f"/chat/{chat.id}", json={"title": "sem token"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_stop_keeps_partial_answer_marked_interrupted(tmp_path) -> None:
    store = await _store(tmp_path)
    llm = _Llm()
    service = ChatService(llm, store)
    first, _, _ = await service.ask("Primeira", on_token=lambda _t: None)
    llm.hang = True
    task = asyncio.create_task(service.ask("Segunda", chat_id=first.id, on_token=lambda _t: None))
    await llm.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)  # a gravação protegida termina fora do cancelamento
    _, messages = await service.get(first.id)
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[-1].content == "Resposta pela metade"
    assert messages[-1].interrupted is True
    assert messages[1].interrupted is False


@pytest.mark.asyncio
async def test_stop_on_new_chat_keeps_question_and_partial(tmp_path) -> None:
    store = await _store(tmp_path)
    llm = _Llm()
    llm.hang = True
    service = ChatService(llm, store)
    task = asyncio.create_task(service.ask("Nova", on_token=lambda _t: None))
    await llm.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    chats = await service.list_chats()
    assert len(chats) == 1
    _, messages = await service.get(chats[0].id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[-1].interrupted is True


@pytest.mark.asyncio
async def test_retry_reuses_unanswered_question(tmp_path) -> None:
    store = await _store(tmp_path)
    llm = _Llm()
    service = ChatService(llm, store)
    chat, _, _ = await service.ask("Primeira", on_token=lambda _t: None)
    llm.fail = True
    with pytest.raises(ConnectionError):
        await service.ask("Segunda", chat_id=chat.id, on_token=lambda _t: None)
    llm.fail = False
    await service.ask("Segunda", chat_id=chat.id, on_token=lambda _t: None, retry=True)
    _, messages = await service.get(chat.id)
    assert [(m.role, m.content) for m in messages if m.role == "user"] == [("user", "Primeira"), ("user", "Segunda")]
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]

    # Última pergunta já respondida: retry não reaproveita, grava a pergunta de novo.
    await service.ask("Segunda", chat_id=chat.id, on_token=lambda _t: None, retry=True)
    _, messages = await service.get(chat.id)
    assert [m.content for m in messages if m.role == "user"] == ["Primeira", "Segunda", "Segunda"]


@pytest.mark.asyncio
async def test_retry_flag_is_accepted_by_ask_endpoint(client: AsyncClient, app) -> None:
    chat, _, _ = await app.state.container.chat.ask("Oi")
    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "Oi", "chat_id": chat.id, "retry": True}
    ) as response:
        assert response.status_code == 200
        body = "".join([line async for line in response.aiter_lines()])
    assert '"done": true' in body


@pytest.mark.asyncio
async def test_client_disconnect_mid_stream_saves_partial(app) -> None:
    """Pela ASGI de verdade: a tela fecha a conexão no meio da resposta (botão Parar)."""
    import json

    container = app.state.container
    llm = _Llm()
    llm.hang = True
    container.chat = ChatService(llm, container.store)
    body = json.dumps({"message": "Pergunta longa"}).encode()
    first_chunk = asyncio.Event()
    sent_body = False

    async def receive() -> dict:
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.body" and b"token" in message.get("body", b""):
            first_chunk.set()

    headers = [(b"content-type", b"application/json"), *((k.lower().encode(), v.encode()) for k, v in auth().items())]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/chat/ask",
        "raw_path": b"/chat/ask",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    await asyncio.sleep(0.05)
    chats = await container.chat.list_chats()
    assert len(chats) == 1
    _, messages = await container.chat.get(chats[0].id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[-1].content == "Resposta pela metade"
    assert messages[-1].interrupted is True
