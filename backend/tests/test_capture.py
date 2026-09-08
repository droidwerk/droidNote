from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.domain.models import AudioChunk
from tests.conftest import auth


@pytest.mark.asyncio
async def test_start_and_stop_capture(client: AsyncClient, app) -> None:
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    body = started.json()
    assert body["recording"] is True
    assert body["session_id"]
    assert body["started_at"]
    assert app.state.container.capture.whisper_loaded() is True

    listed = await client.get("/sessions", headers=auth())
    assert listed.json()[0]["status"] == "recording"

    stopped = await client.post("/capture/stop", headers=auth())
    assert stopped.status_code == 200
    assert stopped.json()["recording"] is False
    # O modelo continua na RAM depois do stop: a próxima gravação começa sem
    # esperar o Whisper carregar de novo.
    assert app.state.container.capture.whisper_loaded() is True


@pytest.mark.asyncio
async def test_stop_returns_when_flush_hangs(client: AsyncClient, app) -> None:
    app.state.container.capture._asr.delay = 4.0  # type: ignore[attr-defined]
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    _push_window(app)
    started_at = time.monotonic()
    stopped = await client.post("/capture/stop", headers=auth())
    elapsed = time.monotonic() - started_at
    assert stopped.status_code == 200
    assert stopped.json()["recording"] is False
    assert elapsed < 2
    await app.state.container.capture.wait_drain(session_id)


@pytest.mark.asyncio
async def test_speech_chunk_becomes_transcript(client: AsyncClient, app) -> None:
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    audio = app.state.container.capture._audio
    window = int(app.state.container.settings.window_seconds * app.state.container.settings.sample_rate)
    assert audio.callback is not None
    audio.callback(
        AudioChunk(
            samples=[0.2] * window,
            sample_rate=app.state.container.settings.sample_rate,
            timestamp_ms=0,
        )
    )
    for _ in range(20):
        segments = await app.state.container.store.list_segments(session_id)
        if segments:
            assert segments[0].text == "olá mundo"
            return
        await asyncio.sleep(0.05)
    raise AssertionError("transcript segment did not appear")


async def _wait_segments(app, session_id: str, count: int = 1, attempts: int = 40):
    for _ in range(attempts):
        segments = await app.state.container.store.list_segments(session_id)
        if len(segments) >= count:
            return segments
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected {count} segments")


def _push_window(app, timestamp_ms: int = 0) -> None:
    audio = app.state.container.capture._audio
    window = int(app.state.container.settings.window_seconds * app.state.container.settings.sample_rate)
    assert audio.callback is not None
    audio.callback(
        AudioChunk(
            samples=[0.2] * window,
            sample_rate=app.state.container.settings.sample_rate,
            timestamp_ms=timestamp_ms,
        )
    )


@pytest.mark.asyncio
async def test_single_participant_stamps_speaker(client: AsyncClient, app) -> None:
    created = await client.post("/people", headers=auth(), json={"name": "Ana"})
    ana = created.json()
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [ana["id"]]},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    _push_window(app)
    segments = await _wait_segments(app, session_id)
    assert segments[0].speaker_id == ana["id"]
    assert segments[0].text == "olá mundo"


@pytest.mark.asyncio
async def test_mic_channel_does_not_peel_name_prefix(client: AsyncClient, app) -> None:
    ana = (await client.post("/people", headers=auth(), json={"name": "Ana"})).json()
    bruno = (await client.post("/people", headers=auth(), json={"name": "Bruno"})).json()
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [ana["id"], bruno["id"]]},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    app.state.container.capture._asr.text = "Ana: olá mundo"  # type: ignore[attr-defined]
    _push_window(app)
    segments = await _wait_segments(app, session_id)
    assert segments[0].source == "mic"
    assert segments[0].speaker_id is None
    assert segments[0].text == "Ana: olá mundo"


@pytest.mark.asyncio
async def test_self_person_after_patch_on_mic(client: AsyncClient, app) -> None:
    ana = (await client.post("/people", headers=auth(), json={"name": "Ana"})).json()
    bruno = (await client.post("/people", headers=auth(), json={"name": "Bruno"})).json()
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [ana["id"], bruno["id"]]},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    _push_window(app, 0)
    first = (await _wait_segments(app, session_id, 1))[0]
    assert first.speaker_id is None
    patched = await client.patch(
        f"/sessions/{session_id}/segments/{first.id}",
        headers=auth(),
        json={"speaker_id": ana["id"]},
    )
    assert patched.status_code == 200
    _push_window(app, 8000)
    second = await _wait_segments(app, session_id, 2)
    tagged = [item for item in second if item.id != first.id]
    assert tagged
    assert tagged[0].speaker_id == ana["id"]


@pytest.mark.asyncio
async def test_loud_empty_window_becomes_scene_tag(client: AsyncClient, app) -> None:
    from app.infrastructure.asr.scene import SCENE_MUSIC

    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    app.state.container.capture._asr.text = ""  # type: ignore[attr-defined]
    audio = app.state.container.capture._audio
    window = int(app.state.container.settings.window_seconds * app.state.container.settings.sample_rate)
    assert audio.callback is not None
    audio.callback(
        AudioChunk(
            samples=[0.2] * window,
            sample_rate=app.state.container.settings.sample_rate,
            timestamp_ms=0,
        )
    )
    for _ in range(20):
        segments = await app.state.container.store.list_segments(session_id)
        if segments:
            assert segments[0].text == SCENE_MUSIC
            return
        await asyncio.sleep(0.05)
    raise AssertionError("scene tag segment did not appear")


@pytest.mark.asyncio
async def test_capture_writes_wav(client: AsyncClient, app) -> None:
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    _push_window(app)
    await _wait_segments(app, session_id)
    await client.post("/capture/stop", headers=auth())
    path = app.state.container.settings.resolve_recordings_dir() / f"{session_id}.wav"
    assert path.exists()
    assert path.stat().st_size > 44


@pytest.mark.asyncio
async def test_capture_skips_wav_when_disabled(client: AsyncClient, app) -> None:
    await client.put("/setup/settings", headers=auth(), json={"save_recordings": False})
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    await client.post("/capture/stop", headers=auth())
    path = app.state.container.settings.resolve_recordings_dir() / f"{session_id}.wav"
    assert not path.exists()


@pytest.mark.asyncio
async def test_capture_stores_mode(client: AsyncClient) -> None:
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "capture_mode": "dictation"},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    await client.post("/capture/stop", headers=auth())
    detail = await client.get(f"/sessions/{session_id}", headers=auth())
    assert detail.json()["session"]["capture_mode"] == "dictation"


@pytest.mark.asyncio
async def test_stop_returns_before_slow_speaker_assign(client: AsyncClient, app) -> None:
    async def hang(_session_id: str):
        await asyncio.sleep(30)
        return []

    app.state.container.speakers.assign_from_context = hang  # type: ignore[method-assign]
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    started_at = time.monotonic()
    stopped = await client.post("/capture/stop", headers=auth())
    elapsed = time.monotonic() - started_at
    assert stopped.status_code == 200
    assert stopped.json()["recording"] is False
    assert elapsed < 3


@pytest.mark.asyncio
async def test_leftover_transcript_stays_on_stopped_session(client: AsyncClient, app) -> None:
    app.state.container.capture._asr.delay = 0.35  # type: ignore[attr-defined]
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    first_id = started.json()["session_id"]
    _push_window(app)
    stopped = await client.post("/capture/stop", headers=auth())
    assert stopped.status_code == 200
    nxt = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert nxt.status_code == 200
    second_id = nxt.json()["session_id"]
    assert second_id != first_id
    segments = await _wait_segments(app, first_id)
    assert segments[0].session_id == first_id
    other = await app.state.container.store.list_segments(second_id)
    assert other == []
    await client.post("/capture/stop", headers=auth())


@pytest.mark.asyncio
async def test_stop_does_not_drop_queued_windows(client: AsyncClient, app) -> None:
    app.state.container.capture._asr.delay = 1.2  # type: ignore[attr-defined]
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    _push_window(app, 0)
    _push_window(app, 25_000)
    _push_window(app, 50_000)
    t0 = time.monotonic()
    stopped = await client.post("/capture/stop", headers=auth())
    assert stopped.status_code == 200
    assert time.monotonic() - t0 < 2
    segments = await _wait_segments(app, session_id, 3, attempts=200)
    assert len(segments) >= 3
    assert all(item.session_id == session_id for item in segments)
