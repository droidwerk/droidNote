from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.models import Session
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from app.main import create_app
from tests.fakes import FakeAudioCapture


def test_lifespan_stops_abandoned_recordings(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    kept_end = datetime(2026, 1, 2, tzinfo=UTC)

    async def seed() -> tuple[str, str, str]:
        store = SqliteStore(settings.db_path)
        await store.initialize()
        recording = Session(
            id=new_id(),
            title="Aberta",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            ended_at=None,
            status="recording",
        )
        idle = Session(
            id=new_id(),
            title="Fechada",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            ended_at=kept_end,
            status="stopped",
        )
        fallen = Session(
            id=new_id(),
            title="Queda",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            ended_at=kept_end,
            status="recording",
        )
        await store.create_session(recording)
        await store.create_session(idle)
        await store.create_session(fallen)
        return recording.id, idle.id, fallen.id

    recording_id, idle_id, fallen_id = asyncio.run(seed())
    monkeypatch.setattr("app.main.WhisperEngine.is_ready", lambda self: False)
    monkeypatch.setattr("app.main.OnnxVoiceEmbedder.is_ready", lambda self: True)
    monkeypatch.setattr("app.main.OnnxVoiceEmbedder.load", lambda self: None)
    monkeypatch.setattr("app.main.build_audio_capture", lambda _rate: FakeAudioCapture())

    with TestClient(create_app(settings)):
        pass

    async def check() -> None:
        store = SqliteStore(settings.db_path)
        recording = await store.get_session(recording_id)
        assert recording is not None
        assert recording.status == "stopped"
        assert recording.ended_at is not None
        idle = await store.get_session(idle_id)
        assert idle is not None
        assert idle.status == "stopped"
        assert idle.ended_at == kept_end
        fallen = await store.get_session(fallen_id)
        assert fallen is not None
        assert fallen.status == "stopped"
        assert fallen.ended_at == kept_end

    asyncio.run(check())
