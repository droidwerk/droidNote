from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from httpx import AsyncClient

from app.application.bus import EventBus
from app.application.summarize import render_transcript, voice_label
from app.application.voices import VoiceService, summarize_voices
from app.domain.models import Session, TranscriptSegment
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth
from tests.fakes import FakeVoiceEmbedder


def _audio(level: float, seconds: float = 2.0) -> np.ndarray:
    # A média do sinal escolhe o protótipo do embedder falso.
    return np.full(int(16_000 * seconds), level, dtype=np.float32)


async def _session(store: SqliteStore, mode: str = "meeting") -> str:
    session = Session(
        id=new_id(),
        title="Teste",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="recording",
        capture_mode=mode,  # type: ignore[arg-type]
    )
    await store.create_session(session)
    return session.id


async def _record(service: VoiceService, store: SqliteStore, session_id: str, plan: list[tuple[float, str]]) -> None:
    clock = 0
    for level, text in plan:
        turns = service.label_window(session_id, "loopback", _audio(level), clock, [(0.0, 1.9, text)])
        assert turns is not None
        for turn in turns:
            segment = TranscriptSegment(
                id=new_id(),
                session_id=session_id,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                text=turn.text,
                source="loopback",
                speaker_cluster=turn.cluster,
                speaker_confidence=turn.confidence,
                speaker_id=turn.person_id,
            )
            await store.add_segment(segment)
            await service.persist_turn(segment, turn)
        clock += 2_500


@pytest.fixture
async def voices(tmp_path) -> tuple[VoiceService, SqliteStore]:
    store = SqliteStore(tmp_path / "voices.db")
    await store.initialize()
    return VoiceService(FakeVoiceEmbedder(), store, EventBus()), store


@pytest.mark.asyncio
async def test_live_labels_split_voices_and_refine_keeps_them(voices) -> None:
    service, store = voices
    session_id = await _session(store)
    assert await service.begin(session_id, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, session_id, [(0.0, "oi"), (0.1, "tudo bem"), (0.0, "sim"), (0.1, "ótimo")])
    segments = await store.list_segments(session_id)
    clusters = [item.speaker_cluster for item in segments]
    assert clusters[0] == clusters[2] and clusters[1] == clusters[3] and clusters[0] != clusters[1]

    refined = await service.refine(session_id, final=True)
    assert [item.speaker_cluster for item in refined] == ["v1", "v2", "v1", "v2"]
    summary = summarize_voices(refined)
    assert [voice.cluster for voice in summary] == ["v1", "v2"]
    assert summary[0].segments == 2


@pytest.mark.asyncio
async def test_naming_a_voice_names_every_turn_and_is_remembered(voices) -> None:
    service, store = voices
    first = await _session(store)
    await service.begin(first, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, first, [(0.0, "a"), (0.1, "b"), (0.0, "c")])
    await service.refine(first, final=True)
    ana = await store.create_person("Ana")
    await service.assign(first, "v1", ana.id)
    named = await store.list_segments(first)
    assert [item.speaker_id for item in named] == [ana.id, None, ana.id]
    assert ana.id in await store.voiceprint_people()

    # Gravação seguinte: a voz da Ana é reconhecida sem rotular nada.
    second = await _session(store)
    await service.begin(second, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, second, [(0.1, "x"), (0.0, "y")])
    later = await store.list_segments(second)
    assert later[1].speaker_id == ana.id
    assert later[0].speaker_id is None


@pytest.mark.asyncio
async def test_locked_turn_keeps_manual_name_after_refine(voices) -> None:
    service, store = voices
    session_id = await _session(store)
    await service.begin(session_id, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, session_id, [(0.0, "a"), (0.0, "b")])
    bruno = await store.create_person("Bruno")
    segment = (await store.list_segments(session_id))[1]
    from dataclasses import replace

    await store.save_segment(replace(segment, speaker_id=bruno.id, speaker_locked=True))
    refined = await service.refine(session_id, final=True)
    assert refined[1].speaker_id == bruno.id
    assert refined[1].speaker_locked is True


@pytest.mark.asyncio
async def test_dictation_links_mic_voice_to_self(voices) -> None:
    service, store = voices
    me = await store.create_person("Eu")
    session_id = await _session(store, mode="dictation")
    await service.begin(session_id, mode="dictation", self_person_id=me.id, call=False)
    turns = service.label_window(session_id, "mic", _audio(0.0), 0, [(0.0, 1.9, "lembrete")])
    assert turns and turns[0].person_id == me.id


@pytest.mark.asyncio
async def test_engine_off_returns_none_so_capture_falls_back(voices) -> None:
    service, store = voices
    service.embedder.ready = False  # type: ignore[union-attr]
    session_id = await _session(store)
    assert await service.begin(session_id, mode="meeting", self_person_id=None, call=True) is False
    assert service.label_window(session_id, "mic", _audio(0.0), 0, [(0.0, 1.0, "oi")]) is None


@pytest.mark.asyncio
async def test_probe_matches_known_voice_without_creating_new_ones(voices) -> None:
    service, store = voices
    session_id = await _session(store)
    await service.begin(session_id, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, session_id, [(0.0, "a")])
    found = service.probe(session_id, _audio(0.0, 1.5))
    assert found is not None and found[0] == "v1"
    assert service.probe(session_id, _audio(0.2, 1.5)) is None


def test_unnamed_voices_reach_the_note_prompt() -> None:
    segments = [
        TranscriptSegment(id="1", session_id="s", start_ms=0, end_ms=1000, text="Proponho sexta.", speaker_cluster="v2"),
        TranscriptSegment(id="2", session_id="s", start_ms=1000, end_ms=2000, text="Fechado.", speaker_id="p1"),
    ]
    rendered = render_transcript(segments, {"p1": "Tomás"}, "pt")
    assert "Voz 2: Proponho sexta." in rendered
    assert "Tomás: Fechado." in rendered
    assert voice_label("v3", "en") == "Speaker 3"


# ------------------------------------------------------------------- API


@pytest.mark.asyncio
async def test_voice_endpoints_name_a_voice(client: AsyncClient, app) -> None:
    container = app.state.container
    store = container.store
    container.voices = VoiceService(FakeVoiceEmbedder(), store, container.bus)
    session_id = await _session(store)
    for index, cluster in enumerate(["v1", "v2", "v1"]):
        await store.add_segment(
            TranscriptSegment(
                id=new_id(),
                session_id=session_id,
                start_ms=index * 1000,
                end_ms=index * 1000 + 900,
                text=f"fala {index}",
                speaker_cluster=cluster,
            )
        )

    listed = await client.get(f"/sessions/{session_id}/voices", headers=auth())
    assert listed.status_code == 200
    body = listed.json()
    assert body["engine_ready"] is True
    assert [voice["cluster"] for voice in body["voices"]] == ["v1", "v2"]

    named = await client.put(f"/sessions/{session_id}/voices/v1", headers=auth(), json={"name": "Carla"})
    assert named.status_code == 200
    voices = {voice["cluster"]: voice for voice in named.json()["voices"]}
    assert voices["v1"]["person_name"] == "Carla"
    assert [item["speaker_name"] for item in named.json()["segments"]] == ["Carla", None, "Carla"]

    missing = await client.put(f"/sessions/{session_id}/voices/v9", headers=auth(), json={"name": "X"})
    assert missing.status_code == 404

    people = await client.get("/people", headers=auth())
    assert any(person["name"] == "Carla" for person in people.json())


@pytest.mark.asyncio
async def test_patching_a_clustered_segment_names_the_whole_voice(client: AsyncClient, app) -> None:
    container = app.state.container
    store = container.store
    container.voices = VoiceService(FakeVoiceEmbedder(), store, container.bus)
    session_id = await _session(store)
    ids = []
    for index, cluster in enumerate(["v1", "v2", "v1"]):
        segment_id = new_id()
        ids.append(segment_id)
        await store.add_segment(
            TranscriptSegment(id=segment_id, session_id=session_id, start_ms=index * 1000, end_ms=index * 1000 + 900, text="x", speaker_cluster=cluster)
        )
    response = await client.patch(
        f"/sessions/{session_id}/segments/{ids[0]}", headers=auth(), json={"name": "Davi", "apply_forward": True}
    )
    assert response.status_code == 200
    segments = await store.list_segments(session_id)
    davi = segments[0].speaker_id
    assert davi and segments[2].speaker_id == davi and segments[1].speaker_id is None
    assert segments[0].speaker_locked is False

    only_this = await client.patch(
        f"/sessions/{session_id}/segments/{ids[1]}", headers=auth(), json={"speaker_id": davi, "apply_forward": False}
    )
    assert only_this.status_code == 200
    assert only_this.json()["speaker_locked"] is True
