from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.domain.models import AudioChunk
from tests.conftest import auth


@pytest.mark.asyncio
async def test_start_capture_rejects_when_asr_not_ready(client: AsyncClient, app) -> None:
    app.state.container.setup._asr.ready = False
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 409
    detail = started.json()["detail"].lower()
    assert "transcrição" in detail
    assert "pronto" in detail or "baixado" in detail


@pytest.mark.asyncio
async def test_start_and_stop_capture(client: AsyncClient, app) -> None:
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200, started.text
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
async def test_single_participant_does_not_replace_chosen_self(client: AsyncClient, app) -> None:
    """Com "você no microfone" escolhido, uma sala com uma só pessoa é a outra
    pessoa da conversa: o microfone continua sendo de quem grava."""
    ana = (await client.post("/people", headers=auth(), json={"name": "Ana"})).json()
    bruno = (await client.post("/people", headers=auth(), json={"name": "Bruno"})).json()
    await app.state.container.store.set_setting("self_person_id", ana["id"])
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [bruno["id"]]},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    _push_window(app)
    segments = await _wait_segments(app, session_id)
    assert segments[0].speaker_id == ana["id"]


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


@pytest.mark.asyncio
async def test_default_title_follows_ui_language(client: AsyncClient, app) -> None:
    app.state.container.settings.ui_language = "en"
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "capture_mode": "lecture"},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    detail = await client.get(f"/sessions/{session_id}", headers=auth())
    assert detail.json()["session"]["title"].startswith("Lecture ")
    await client.post("/capture/stop", headers=auth())


@pytest.mark.asyncio
async def test_word_times_drop_repeated_short_phrase(client: AsyncClient, app) -> None:
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    capture = app.state.container.capture
    scripts = [
        [(10.0, 12.0, "reunião"), (19.2, 19.7, "ok")],
        [(0.2, 0.7, "ok"), (2.0, 3.0, "seguimos")],
    ]

    def transcribe_words(samples, sample_rate, *, language=None):
        del samples, sample_rate, language
        return list(scripts.pop(0)), "pt"

    capture._asr.transcribe_words = transcribe_words  # type: ignore[method-assign]
    await capture._transcribe([0.2], 0, 20_000, "mic", session_id)
    await capture._transcribe([0.2], 19_000, 39_000, "mic", session_id)
    segments = await app.state.container.store.list_segments(session_id)
    assert [item.text for item in segments] == ["reunião ok", "seguimos"]
    await client.post("/capture/stop", headers=auth())


# --- Bolha de reunião: pausa (C10) e alerta de silêncio (C8, C9) ---


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _chunk(app, seconds: float, level: float, timestamp_ms: int = 0) -> AudioChunk:
    rate = app.state.container.settings.sample_rate
    return AudioChunk(samples=[level] * int(rate * seconds), sample_rate=rate, timestamp_ms=timestamp_ms)


async def _start_idle(client: AsyncClient, app) -> tuple[_Clock, asyncio.Queue]:
    clock = _Clock()
    app.state.container.capture._clock = clock
    events = await app.state.container.bus.subscribe()
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    assert started.status_code == 200
    return clock, events


def _idle_events(queue: asyncio.Queue) -> list[dict]:
    out = []
    while not queue.empty():
        event = queue.get_nowait()
        if event.get("type") == "idle_alert":
            out.append(event)
    return out


@pytest.mark.asyncio
async def test_idle_alert_asks_silence_then_clears_on_speech(client: AsyncClient, app) -> None:
    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture
    capture._audio.callback(_chunk(app, 1.0, 0.0))
    clock.now += 299
    await capture.idle_tick()
    assert _idle_events(events) == []
    clock.now += 1
    await capture.idle_tick()
    [asked] = _idle_events(events)
    assert asked["status"] == "asked" and asked["kind"] == "silence"
    assert asked["session_id"] == capture.state.session_id
    assert capture.idle_alert == {"kind": "silence"}
    # 2 s de fala não bastam; 3 s seguidos limpam a pergunta.
    capture._audio.callback(_chunk(app, 2.0, 0.2))
    await capture.idle_tick()
    assert _idle_events(events) == []
    capture._audio.callback(_chunk(app, 1.0, 0.2))
    await capture.idle_tick()
    [cleared] = _idle_events(events)
    assert cleared["status"] == "cleared"
    assert capture.idle_alert is None


@pytest.mark.asyncio
async def test_idle_alert_kind_music_when_energy_without_speech(client: AsyncClient, app) -> None:
    import numpy as np

    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture

    class _NoSpeech:
        def mask(self, samples):
            return np.zeros(len(samples), dtype=bool)

    # Silero dizendo "sem fala" num áudio alto = música.
    capture._neural_vad = True
    capture._mic_vad = _NoSpeech()
    for _ in range(10):
        capture._audio.callback(_chunk(app, 0.5, 0.2))
    clock.now += 300
    await capture.idle_tick()
    [asked] = _idle_events(events)
    assert asked["kind"] == "music"


@pytest.mark.asyncio
async def test_idle_alert_auto_pauses_after_unanswered(client: AsyncClient, app) -> None:
    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture
    clock.now += 300
    await capture.idle_tick()
    clock.now += 119
    await capture.idle_tick()
    assert [item["status"] for item in _idle_events(events)] == ["asked"]
    clock.now += 1
    await capture.idle_tick()
    assert [item["status"] for item in _idle_events(events)] == ["auto_paused"]
    assert capture.state.paused is True
    assert capture.state.recording is True


@pytest.mark.asyncio
async def test_idle_alert_off_by_setting_or_pause(client: AsyncClient, app) -> None:
    saved = await client.put("/setup/settings", headers=auth(), json={"silence_alert": False})
    assert saved.json()["silence_alert"] is False
    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture
    clock.now += 1000
    await capture.idle_tick()
    assert _idle_events(events) == []
    await client.post("/capture/stop", headers=auth())

    await client.put("/setup/settings", headers=auth(), json={"silence_alert": True})
    await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    await client.post("/capture/pause", headers=auth())
    clock.now += 1000
    await capture.idle_tick()
    assert _idle_events(events) == []


@pytest.mark.asyncio
async def test_idle_alert_dismiss_resets_timer(client: AsyncClient, app) -> None:
    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture
    clock.now += 300
    await capture.idle_tick()
    dismissed = await client.post("/capture/idle-alert/dismiss", headers=auth())
    assert dismissed.status_code == 200
    assert [item["status"] for item in _idle_events(events)] == ["asked", "dismissed"]
    assert capture.idle_alert is None
    clock.now += 299
    await capture.idle_tick()
    assert _idle_events(events) == []
    # "Encerrar e gerar nota" é o stop de sempre.
    stopped = await client.post("/capture/stop", headers=auth())
    assert stopped.json()["recording"] is False


@pytest.mark.asyncio
async def test_pause_endpoints_require_token(client: AsyncClient) -> None:
    for path in ("/capture/pause", "/capture/resume", "/capture/idle-alert/dismiss"):
        assert (await client.post(path)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_pause_drops_audio_and_resume_keeps_session(client: AsyncClient, app) -> None:
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    session_id = started.json()["session_id"]
    capture = app.state.container.capture
    window = app.state.container.settings.window_seconds

    paused = await client.post("/capture/pause", headers=auth())
    assert paused.status_code == 200
    assert paused.json()["paused"] is True
    assert paused.json()["recording"] is True
    capture._audio.callback(_chunk(app, window, 0.2, timestamp_ms=0))
    await asyncio.sleep(0.2)
    assert await app.state.container.store.list_segments(session_id) == []
    session = await app.state.container.store.get_session(session_id)
    assert session.status == "recording"

    resumed = await client.post("/capture/resume", headers=auth())
    assert resumed.json()["paused"] is False
    assert resumed.json()["session_id"] == session_id
    # O relógio do driver andou durante a pausa; o trecho tem que cair no tempo do WAV.
    capture._audio.callback(_chunk(app, window, 0.2, timestamp_ms=int(window * 1000)))
    segments = await _wait_segments(app, session_id)
    assert segments[0].start_ms < 500

    await client.post("/capture/stop", headers=auth())
    await capture.wait_drain(session_id)
    path = app.state.container.settings.resolve_recordings_dir() / f"{session_id}.wav"
    rate = app.state.container.settings.sample_rate
    # Só o áudio depois do resume foi gravado (cabeçalho 44 B + PCM 16 bits).
    assert path.stat().st_size == 44 + int(rate * window) * 2


class _FakeSocket:
    """Recebe só o hello e desconecta: basta para provar o que o WS manda ao abrir."""

    def __init__(self, app) -> None:
        self.app = app
        self.headers = {"X-DroidNote-Token": auth()["X-DroidNote-Token"]}
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def close(self, code: int = 1000) -> None:
        raise AssertionError(f"socket closed {code}")

    async def send_json(self, data: dict) -> None:
        from fastapi import WebSocketDisconnect

        self.sent.append(data)
        raise WebSocketDisconnect()


@pytest.mark.asyncio
async def test_hello_and_capture_event_carry_pause_and_pending_alert(client: AsyncClient, app) -> None:
    from app.api.v1.endpoints.ws import transcript_socket

    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture
    clock.now += 10_000
    await capture.idle_tick()
    socket = _FakeSocket(app)
    await transcript_socket(socket)  # type: ignore[arg-type]
    [hello] = socket.sent
    assert hello["type"] == "hello"
    assert hello["paused"] is False
    assert hello["idle_alert"] == {"kind": "silence"}

    while not events.empty():
        events.get_nowait()
    await client.post("/capture/pause", headers=auth())
    [event] = [item for item in _drain(events) if item.get("type") == "capture"]
    assert event["paused"] is True
    socket = _FakeSocket(app)
    await transcript_socket(socket)  # type: ignore[arg-type]
    assert socket.sent[0]["paused"] is True
    assert socket.sent[0]["idle_alert"] is None


def _drain(queue: asyncio.Queue) -> list[dict]:
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


# --- Alerta de silêncio com música e fala curta (pós-2.4, bug B) ---


async def _tick_until_asked(capture, clock, events, feed, limit_s: int) -> tuple[list[dict], float]:
    """Alimenta 1 s de áudio por segundo do relógio e roda o tick, até a pergunta."""
    start = clock.now
    while clock.now - start < limit_s:
        feed(clock.now - start)
        clock.now += 1
        await capture.idle_tick()
        asked = _idle_events(events)
        if asked:
            return asked, clock.now - start
    return [], clock.now - start


@pytest.mark.asyncio
async def test_idle_alert_music_with_vocals_on_system_channel(client: AsyncClient, app) -> None:
    import numpy as np

    clock = _Clock()
    capture = app.state.container.capture
    capture._clock = clock
    events = await app.state.container.bus.subscribe()
    assert (await client.post("/capture/start", headers=auth(), json={})).status_code == 200
    capture.state.mic_only = False
    rate = app.state.container.settings.sample_rate

    class _Vad:
        def __init__(self, speech: bool) -> None:
            self.speech = speech

        def mask(self, samples):
            return np.full(len(samples), self.speech, dtype=bool)

    # Silero vê "fala" o tempo todo na música do sistema; o microfone está mudo.
    capture._neural_vad = True
    capture._mic_vad = _Vad(False)
    capture._loop_vad = _Vad(True)

    def feed(_t: float) -> None:
        capture._audio.callback(
            AudioChunk(samples=[0.0] * rate, sample_rate=rate, timestamp_ms=0, mic=[0.0] * rate, loopback=[0.2] * rate)
        )

    asked, elapsed = await _tick_until_asked(capture, clock, events, feed, 420)
    assert [item["kind"] for item in asked] == ["music"]
    # ~45 s para reconhecer a música + 300 s do alerta.
    assert elapsed < 360

    # Fala "no sistema" com música não limpa o alerta; fala no microfone limpa.
    tenth = rate // 10

    def push(mic_level: float) -> None:
        capture._audio.callback(
            AudioChunk(
                samples=[0.0] * tenth, sample_rate=rate, timestamp_ms=0, mic=[mic_level] * tenth, loopback=[0.2] * tenth
            )
        )

    for _ in range(50):
        push(0.0)
    await capture.idle_tick()
    assert _idle_events(events) == []
    assert capture.idle_alert == {"kind": "music"}
    capture._mic_vad = _Vad(True)
    for _ in range(31):
        push(0.2)
    await capture.idle_tick()
    assert [item["status"] for item in _idle_events(events)] == ["cleared"]


@pytest.mark.asyncio
async def test_idle_alert_not_asked_for_mic_conversation_over_room_noise(client: AsyncClient, app) -> None:
    import numpy as np

    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture

    class _Vad:
        speech = False

        def mask(self, samples):
            return np.full(len(samples), self.speech, dtype=bool)

    vad = _Vad()
    capture._neural_vad = True
    capture._mic_vad = vad

    def feed(t: float) -> None:
        # Ruído de sala contínuo acima do limiar; fala 2 s, pausa 3 s.
        vad.speech = t % 5 < 2
        capture._audio.callback(_chunk(app, 1.0, 0.05))

    asked, _ = await _tick_until_asked(capture, clock, events, feed, 420)
    assert asked == []


@pytest.mark.asyncio
async def test_idle_alert_not_asked_during_conversation_with_pauses(client: AsyncClient, app) -> None:
    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture

    def feed(t: float) -> None:
        # 2 s falando, 3 s de pausa, o tempo todo.
        capture._audio.callback(_chunk(app, 1.0, 0.2 if t % 5 < 2 else 0.0))

    asked, _ = await _tick_until_asked(capture, clock, events, feed, 420)
    assert asked == []


@pytest.mark.asyncio
async def test_idle_alert_short_blips_do_not_reset_silence(client: AsyncClient, app) -> None:
    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture

    def feed(t: float) -> None:
        if t % 30 == 0:
            # Estalo de ~100 ms que o VAD chama de fala.
            capture._audio.callback(_chunk(app, 0.1, 0.2))
            capture._audio.callback(_chunk(app, 0.9, 0.0))
        else:
            capture._audio.callback(_chunk(app, 1.0, 0.0))

    asked, elapsed = await _tick_until_asked(capture, clock, events, feed, 320)
    assert [item["kind"] for item in asked] == ["silence"]
    assert elapsed == 300


# --- Fim do evento da agenda (planned_end) ---


async def _start_event(client: AsyncClient, app, **settings) -> tuple[_Clock, asyncio.Queue, dict]:
    from datetime import UTC, datetime, timedelta

    if settings:
        await client.put("/setup/settings", headers=auth(), json=settings)
    end = datetime.now(tz=UTC) + timedelta(hours=1)
    wall = {"now": end - timedelta(seconds=1)}
    capture = app.state.container.capture
    capture._wall = lambda: wall["now"]
    clock = _Clock()
    capture._clock = clock
    events = await app.state.container.bus.subscribe()
    started = await client.post(
        "/capture/start", headers=auth(), json={"mic_only": True, "planned_end": end.isoformat()}
    )
    assert started.status_code == 200, started.text
    assert capture._planned_end == end
    wall["end"] = end
    return clock, events, wall


@pytest.mark.asyncio
async def test_event_end_asks_even_with_silence_alert_off_and_stops_without_speech(
    client: AsyncClient, app
) -> None:
    clock, events, wall = await _start_event(client, app, silence_alert=False)
    capture = app.state.container.capture
    stopped: list[str] = []

    async def on_auto_stop() -> None:
        stopped.append(capture.state.session_id)
        await capture.stop()

    capture.on_auto_stop = on_auto_stop
    await capture.idle_tick()
    assert _idle_events(events) == []
    wall["now"] = wall["end"]
    await capture.idle_tick()
    [asked] = _idle_events(events)
    assert asked["status"] == "asked" and asked["kind"] == "event_end" and asked["deadline_s"] == 120
    assert capture.idle_alert == {"kind": "event_end"}
    clock.now += 119
    await capture.idle_tick()
    assert _idle_events(events) == []
    clock.now += 1
    await capture.idle_tick()
    [done] = _idle_events(events)
    assert done["status"] == "auto_stopped" and done["kind"] == "event_end"
    await capture._auto_stop_task
    assert stopped and capture.state.recording is False
    session = await app.state.container.store.get_session(stopped[0])
    assert session.status == "stopped"


@pytest.mark.asyncio
async def test_event_end_keeps_recording_when_people_still_talk(client: AsyncClient, app) -> None:
    clock, events, wall = await _start_event(client, app)
    capture = app.state.container.capture
    wall["now"] = wall["end"]
    await capture.idle_tick()
    assert [item["status"] for item in _idle_events(events)] == ["asked"]
    clock.now += 30
    capture._audio.callback(_chunk(app, 3.0, 0.2))
    clock.now += 90
    await capture.idle_tick()
    assert [item["status"] for item in _idle_events(events)] == ["cleared"]
    assert capture.state.recording is True and capture.idle_alert is None
    # Nunca pergunta de novo; o silêncio de sempre segue valendo.
    clock.now += 299
    await capture.idle_tick()
    assert _idle_events(events) == []
    clock.now += 1
    await capture.idle_tick()
    assert [(item["status"], item["kind"]) for item in _idle_events(events)] == [("asked", "silence")]


@pytest.mark.asyncio
async def test_event_end_continue_never_asks_again(client: AsyncClient, app) -> None:
    from datetime import timedelta

    clock, events, wall = await _start_event(client, app)
    capture = app.state.container.capture
    wall["now"] = wall["end"]
    await capture.idle_tick()
    dismissed = await client.post("/capture/idle-alert/dismiss", headers=auth())
    assert dismissed.status_code == 200
    assert [(item["status"], item["kind"]) for item in _idle_events(events)] == [
        ("asked", "event_end"),
        ("dismissed", "event_end"),
    ]
    clock.now += 200
    wall["now"] = wall["end"] + timedelta(minutes=5)
    await capture.idle_tick()
    assert _idle_events(events) == []
    assert capture.state.recording is True


@pytest.mark.asyncio
async def test_start_ignores_bad_planned_end_and_rejects_bad_type(client: AsyncClient, app) -> None:
    from datetime import UTC, datetime, timedelta

    capture = app.state.container.capture
    now = datetime.now(tz=UTC)
    for value in (
        (now - timedelta(minutes=1)).isoformat(),
        (now + timedelta(hours=25)).isoformat(),
        (now + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
    ):
        started = await client.post("/capture/start", headers=auth(), json={"mic_only": True, "planned_end": value})
        assert started.status_code == 200, started.text
        assert capture._planned_end is None
        await client.post("/capture/stop", headers=auth())
    bad = await client.post("/capture/start", headers=auth(), json={"mic_only": True, "planned_end": "amanhã"})
    assert bad.status_code == 422
    no_auth = await client.post("/capture/start", json={"mic_only": True})
    assert no_auth.status_code in (401, 403)


@pytest.mark.asyncio
async def test_calendar_auto_record_setting_defaults_on(client: AsyncClient) -> None:
    got = await client.get("/setup/settings", headers=auth())
    assert got.json()["calendar_auto_record"] is True
    saved = await client.put("/setup/settings", headers=auth(), json={"calendar_auto_record": False})
    assert saved.json()["calendar_auto_record"] is False


@pytest.mark.asyncio
async def test_idle_speech_needs_voice_in_half_the_mic_block(client: AsyncClient, app) -> None:
    import numpy as np

    clock, events = await _start_idle(client, app)
    capture = app.state.container.capture

    class _OneFrame:
        # Ruído de sala: o Silero acende um quadro solto em cada bloco.
        def mask(self, samples):
            out = np.zeros(len(samples), dtype=bool)
            out[: len(samples) // 4] = True
            return out

    capture._neural_vad = True
    capture._mic_vad = _OneFrame()
    rate = app.state.container.settings.sample_rate
    tenth = rate // 10

    def feed(_t: float) -> None:
        for _ in range(10):
            capture._audio.callback(AudioChunk(samples=[0.05] * tenth, sample_rate=rate, timestamp_ms=0))

    asked, elapsed = await _tick_until_asked(capture, clock, events, feed, 320)
    assert asked and asked[0]["status"] == "asked"
    assert elapsed == 300
