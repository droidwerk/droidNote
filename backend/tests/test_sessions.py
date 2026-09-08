from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.domain.models import Session, TranscriptSegment
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth


@pytest.mark.asyncio
async def test_session_lifecycle_and_fts(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    session = Session(
        id=new_id(),
        title="Standup",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
        language="pt",
    )
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(
            id=new_id(),
            session_id=session.id,
            start_ms=0,
            end_ms=4000,
            text="Vamos revisar o backlog do DroidNote amanhã",
            language="pt",
        )
    )
    await store.add_segment(
        TranscriptSegment(
            id=new_id(),
            session_id=session.id,
            start_ms=4000,
            end_ms=8000,
            text="The budget is approved",
            language="en",
        )
    )

    listed = await client.get("/sessions", headers=auth())
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "Standup"

    renamed = await client.patch(
        f"/sessions/{session.id}",
        headers=auth(),
        json={"title": "Standup semanal"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Standup semanal"

    found = await client.get("/sessions/search", headers=auth(), params={"q": "DroidNote"})
    assert found.status_code == 200
    assert len(found.json()["segments"]) == 1

    scoped = await client.get(
        f"/sessions/{session.id}/search",
        headers=auth(),
        params={"q": "budget"},
    )
    assert scoped.status_code == 200
    assert "budget" in scoped.json()["segments"][0]["text"].lower()

    exported = await client.get(f"/sessions/{session.id}/export", headers=auth())
    assert exported.status_code == 200
    assert "Standup semanal" in exported.text

    deleted = await client.delete(f"/sessions/{session.id}", headers=auth())
    assert deleted.status_code == 204
    assert await store.get_session(session.id) is None
    assert await store.list_segments(session.id) == []
    assert await store.get_summary(session.id) is None


@pytest.mark.asyncio
async def test_summarize_persists_structured_fields(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    session = Session(
        id=new_id(),
        title="Alinhamento",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
    )
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(
            id=new_id(),
            session_id=session.id,
            start_ms=0,
            end_ms=2000,
            text="Decidimos lançar na sexta. Ana vai enviar o deck.",
            language="pt",
        )
    )
    app.state.container.setup._whisper_status.status = "ready"  # type: ignore[attr-defined]

    # Fake LLM is used; mark ollama as ready by stubbing status_component
    async def ready_status():
        from app.domain.models import SetupComponentStatus

        return SetupComponentStatus(status="ready", progress=100, message="ok")

    app.state.container.llm.status_component = ready_status  # type: ignore[method-assign]

    response = await client.post(f"/sessions/{session.id}/summarize", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert body["highlights"] == ["Ponto A"]
    assert body["decisions"] == ["Decisão B"]
    assert body["action_items"][0]["text"] == "Fazer C"
    assert body["action_items"][0]["owner"] == "Ana"
    assert body["notes_markdown"]
    assert "Reunião de teste" in body["notes_markdown"]
