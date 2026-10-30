from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from httpx import AsyncClient

from app.application.bus import EventBus
from app.application.summarize import render_transcript, voice_label
from app.application.voices import LiveVoices, VoiceService, _split_named, summarize_voices
from app.infrastructure.voice.tracker import SpeakerTracker
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
    # Janelas de 2 s: a segunda voz só nasce quando acumula fala suficiente.
    assert clusters[0] == clusters[2] == "v1"
    assert clusters[1] is None and clusters[3] == "v2"

    refined = await service.refine(session_id, final=True)
    assert [item.speaker_cluster for item in refined] == ["v1", "v2", "v1", "v2"]
    summary = summarize_voices(refined)
    assert [voice.cluster for voice in summary] == ["v1", "v2"]
    assert summary[0].segments == 2


@pytest.mark.asyncio
async def test_refine_holds_voice_count_until_it_repeats() -> None:
    rng = np.random.default_rng(31)
    centers = [c / np.linalg.norm(c) for c in rng.normal(size=(3, 64))]
    units = np.stack(
        [(c + rng.normal(scale=0.9 / 8, size=64)) for c in centers for _ in range(30)]
    ).astype(np.float32)
    units /= np.linalg.norm(units, axis=1, keepdims=True)
    three = [index // 30 for index in range(90)]
    live = LiveVoices(session_id="s", mode="meeting", self_person_id=None, call=True, tracker=SpeakerTracker())

    # Rodadas iniciais: nada é segurado, as vozes ainda estão chegando.
    two = [0 if index < 60 else 1 for index in range(90)]
    assert len(set(await VoiceService._settle_count(live, units, two, False))) == 2
    assert len(set(await VoiceService._settle_count(live, units, three, False))) == 3
    live.refines = 4

    first = await VoiceService._settle_count(live, units, three, False)
    assert len(set(first)) == 3 and live.accepted_count == 3
    # Uma rodada propõe 2 vozes: fica em espera, a sessão segue com 3.
    held = await VoiceService._settle_count(live, units, two, False)
    assert len(set(held)) == 3 and live.accepted_count == 3 and live.candidate_count == 2
    # Voltou a 3: o candidato cai.
    again = await VoiceService._settle_count(live, units, three, False)
    assert len(set(again)) == 3 and live.candidate_count is None
    # 2 vozes em duas rodadas seguidas: aceito.
    await VoiceService._settle_count(live, units, two, False)
    settled = await VoiceService._settle_count(live, units, two, False)
    assert len(set(settled)) == 2 and live.accepted_count == 2


def test_split_named_never_merges_two_named_voices() -> None:
    rng = np.random.default_rng(41)
    ana_voice, bruno_voice = (c / np.linalg.norm(c) for c in rng.normal(size=(2, 64)))
    units = np.stack(
        [ana_voice + rng.normal(scale=0.05, size=64) for _ in range(6)]
        + [bruno_voice + rng.normal(scale=0.05, size=64) for _ in range(6)]
    ).astype(np.float32)
    units /= np.linalg.norm(units, axis=1, keepdims=True)
    owners = [f"a{i}" for i in range(6)] + [f"b{i}" for i in range(6)]
    by_id = {}
    for index, owner in enumerate(owners):
        by_id[owner] = TranscriptSegment(
            id=owner,
            session_id="s",
            start_ms=index * 3_000,
            end_ms=index * 3_000 + 3_000,
            text="x",
            source="loopback",
            speaker_cluster="v1" if owner.startswith("a") else "v2",
        )
    links = {"v1": "ana", "v2": "bruno"}
    merged = [0] * 12
    split = _split_named(units, owners, merged, by_id, links)
    assert len(set(split)) == 2
    assert len(set(split[:6])) == 1 and len(set(split[6:])) == 1 and split[0] != split[6]
    # Sem pessoas diferentes no grupo, nada muda.
    assert _split_named(units, owners, merged, by_id, {"v1": "ana", "v2": "ana"}) == merged
    # Duas "pessoas" com a mesma impressão vocal são um erro de rótulo, não duas vozes.
    same = np.stack([ana_voice + rng.normal(scale=0.05, size=64) for _ in range(12)]).astype(np.float32)
    same /= np.linalg.norm(same, axis=1, keepdims=True)
    assert _split_named(same, owners, merged, by_id, links) == merged


@pytest.mark.asyncio
async def test_refine_keeps_a_name_when_its_voice_is_absorbed(voices) -> None:
    service, store = voices
    session_id = await _session(store)
    await service.begin(session_id, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, session_id, [(0.0, "a"), (0.0, "b"), (0.0, "c")])
    # O usuário dá nome a uma voz que o motor, por engano, tinha separado da v1.
    marlon = await store.create_person("Marlon")
    segments = await store.list_segments(session_id)
    from dataclasses import replace

    await store.save_segment(replace(segments[2], speaker_cluster="v9"))
    await store.assign_cluster_person(session_id, "v9", marlon.id)
    # O reagrupamento junta tudo numa voz só (é a mesma voz): o nome não some.
    refined = await service.refine(session_id, final=True)
    assert {item.speaker_cluster for item in refined} == {"v1"}
    assert all(item.speaker_id == marlon.id for item in refined)


@pytest.mark.asyncio
async def test_refine_keeps_one_voice_per_person_and_forgets_automatic_links(voices) -> None:
    service, store = voices
    session_id = await _session(store)
    await service.begin(session_id, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, session_id, [(0.0, "a"), (0.1, "b"), (0.0, "c"), (0.1, "d"), (0.1, "e")])
    await service.refine(session_id, final=False)
    ana = await store.create_person("Ana")
    # Duas vozes vinculadas à mesma pessoa (sessão antiga ou engano): fica uma.
    await store.assign_cluster_person(session_id, "v1", ana.id)
    await store.assign_cluster_person(session_id, "v2", ana.id)
    refined = await service.refine(session_id, final=True)
    people = {item.speaker_cluster: item.speaker_id for item in refined}
    assert list(people.values()).count(ana.id) == 1
    links = await store.list_session_voices(session_id)
    assert list(links.values()).count(ana.id) == 1
    # Reconhecimento automático por impressão vocal não vira vínculo gravado.
    other = await _session(store)
    await service.begin(other, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, other, [(0.1, "x"), (0.0, "y"), (0.1, "z")])
    await service.refine(other, final=True)
    assert await store.list_session_voices(other) == {}


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


@pytest.mark.asyncio
async def test_probe_names_a_known_person_before_any_transcript(voices) -> None:
    service, store = voices
    first = await _session(store)
    await service.begin(first, mode="meeting", self_person_id=None, call=True)
    await _record(service, store, first, [(0.0, "a"), (0.1, "b")])
    await service.refine(first, final=True)
    ana = await store.create_person("Ana")
    await service.assign(first, "v1", ana.id)

    second = await _session(store)
    await service.begin(second, mode="meeting", self_person_id=None, call=True)
    # Nenhuma fala transcrita ainda: a primeira sonda só anota, a segunda confirma o nome.
    assert service.probe(second, _audio(0.0, 1.5)) is None
    found = service.probe(second, _audio(0.0, 1.5))
    assert found is not None and found[0] is None and found[1] == ana.id
    # Voz desconhecida zera a confirmação; a Ana precisa de duas sondas de novo.
    assert service.probe(second, _audio(0.1, 1.5)) is None
    assert service.probe(second, _audio(0.0, 1.5)) is None
    assert service.probe(second, _audio(0.0, 1.5)) == (None, ana.id, 1.0)
    # Depois de uma fala dela, a sonda devolve a voz da sessão já com o nome.
    await _record(service, store, second, [(0.0, "oi")])
    assert service.probe(second, _audio(0.0, 1.5)) == ("v1", ana.id, 1.0)


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
