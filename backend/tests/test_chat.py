from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.domain.models import Session, TranscriptSegment
from app.infrastructure.asr.whisper_engine import _segment_is_speech
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth


class _Seg:
    def __init__(self, no_speech: float, logprob: float) -> None:
        self.no_speech_prob = no_speech
        self.avg_logprob = logprob


def test_segment_quality_gates_drop_silence_hallucinations() -> None:
    assert _segment_is_speech(_Seg(0.9, -0.2)) is False
    assert _segment_is_speech(_Seg(0.1, -1.5)) is False
    assert _segment_is_speech(_Seg(0.2, -0.4)) is True


@pytest.mark.asyncio
async def test_chat_uses_transcripts_and_stays_generalist(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    session = Session(
        id=new_id(),
        title="Aula de grafos",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
        language="pt",
        capture_mode="lecture",
    )
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(
            id=new_id(),
            session_id=session.id,
            start_ms=12_000,
            end_ms=20_000,
            text="Dijkstra encontra o caminho mais curto em um grafo com pesos positivos.",
            language="pt",
        )
    )

    listed = await client.get("/chat", headers=auth())
    assert listed.status_code == 200
    assert listed.json() == []

    chunks: list[str] = []
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "O que é Dijkstra nesta aula?", "session_id": session.id},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line:
                chunks.append(line)

    payload = "\n".join(chunks)
    assert "data:" in payload
    assert "Dijkstra" in payload or "grafo" in payload.lower() or "Sobre:" in payload

    after = await client.get("/chat", headers=auth())
    assert after.status_code == 200
    assert len(after.json()) == 1
    chat_id = after.json()[0]["id"]
    detail = await client.get(f"/chat/{chat_id}", headers=auth())
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["citations"]
    assert messages[1]["citations"][0]["session_title"] == "Aula de grafos"


@pytest.mark.asyncio
async def test_chat_answers_in_ui_language_not_transcript_language(
    client: AsyncClient, app
) -> None:
    """Idioma da ferramenta manda na resposta; o idioma da transcrição não."""
    container = app.state.container
    container.settings.language = "pt"
    container.settings.ui_language = "en"
    llm = container.chat._llm

    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "O que é Dijkstra?"}
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    assert "Write every reply in English" in (llm.last_system or "")

    # O cliente pode mandar o idioma junto e ele ganha do settings do backend.
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "O que é Dijkstra?", "ui_language": "es"},
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    assert "Write every reply in Spanish" in (llm.last_system or "")
