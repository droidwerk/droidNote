from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from httpx import AsyncClient

from app.application import chat as chat_module
from app.application.chat import ChatService
from app.infrastructure.persistence.sqlite import SqliteStore
from tests.conftest import auth


class _StallLlm:
    """Manda dois tokens e depois trava (`hang`) ou estoura o timeout do httpx."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        return "ok"

    async def generate_text_stream(self, prompt: str, on_token, *, system: str | None = None) -> str:
        on_token("Item 1 [1] [2] [3] [4] [5]. ")
        on_token("Item 2")
        if self.mode == "hang":
            await asyncio.sleep(3600)
        raise httpx.ReadTimeout("ollama silent for 120s")


@pytest.mark.parametrize("mode", ["hang", "timeout"])
async def test_stalled_stream_saves_partial_as_interrupted(tmp_path, monkeypatch, mode) -> None:
    monkeypatch.setattr(chat_module, "STREAM_STALL_S", 0.2)
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    service = ChatService(_StallLlm(mode), store)
    with pytest.raises((TimeoutError, httpx.TimeoutException)):
        await asyncio.wait_for(service.ask("Pergunta", on_token=lambda _t: None), 5)
    chat = (await store.list_chats())[0]
    stored = (await store.list_chat_messages(chat.id))[-1]
    assert stored.role == "assistant" and stored.interrupted is True
    assert stored.content.startswith("Item 1") and stored.content.endswith("Item 2")
    assert stored.content.count("[") == 3  # teto de citações vale para o parcial


@pytest.mark.parametrize("mode", ["hang", "timeout"])
async def test_stalled_stream_ends_sse_with_error(client: AsyncClient, app, monkeypatch, mode) -> None:
    monkeypatch.setattr(chat_module, "STREAM_STALL_S", 0.2)
    app.state.container.chat._llm = _StallLlm(mode)

    async def read() -> list[dict]:
        events = []
        async with client.stream("POST", "/chat/ask", headers=auth(), json={"message": "Flashcards"}) as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))
        return events

    events = await asyncio.wait_for(read(), 5)
    assert events[-1].get("error")
    chat_id = events[0]["chat_id"]
    messages = (await client.get(f"/chat/{chat_id}", headers=auth())).json()["messages"]
    assert messages[-1]["role"] == "assistant" and messages[-1]["interrupted"] is True


async def test_ollama_stream_raises_when_model_goes_silent(monkeypatch) -> None:
    """Caminho da ata e do chat no Ollama: tokens e depois silêncio terminam em ReadTimeout."""
    from app.infrastructure.llm import ollama_manager

    async def handler(reader, writer) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nTransfer-Encoding: chunked\r\n\r\n")
        line = (json.dumps({"response": "tok "}) + "\n").encode()
        writer.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
        await writer.drain()
        await asyncio.sleep(3600)

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(ollama_manager, "STALL_TIMEOUT_S", 0.3)
    manager = ollama_manager.OllamaManager(f"http://127.0.0.1:{port}", "x")
    tokens: list[str] = []
    with pytest.raises(httpx.ReadTimeout):
        await asyncio.wait_for(manager.generate_json_stream("p", tokens.append), 5)
    assert tokens == ["tok "]
    server.close()
