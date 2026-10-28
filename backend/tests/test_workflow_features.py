from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.application.bus import EventBus
from app.application.meetings import END_AFTER_S, START_AFTER_S, MeetingWatcher, normalize_mode
from app.application.summarize import SummarizeService, parse_summary_json, summary_to_markdown
from app.application.templates import BUILTINS, TemplateService
from app.domain.models import Session, TranscriptSegment, UserNote
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from app.infrastructure.system.mic_usage import meeting_app_label
from tests.conftest import auth

# ------------------------------------------------------------- detecção


def test_meeting_app_labels_from_registry_keys() -> None:
    assert meeting_app_label("C:#Program Files#Google#Chrome#Application#chrome.exe") == "Google Chrome"
    assert meeting_app_label("MSTeams_8wekyb3d8bbwe") == "Microsoft Teams"
    assert meeting_app_label("C:#Users#x#AppData#Roaming#Zoom#bin#Zoom.exe") == "Zoom"
    assert meeting_app_label("C:#Program Files#Python314#python.exe") is None
    assert meeting_app_label("#DroidNote#resources#droidnote-backend#droidnote-backend.exe") is None


@dataclass(frozen=True)
class _User:
    key: str
    app: str
    in_use: bool
    browser: bool = False


class _Probe:
    def available(self) -> bool:
        return True

    def snapshot(self) -> list:
        return []


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Capture:
    def __init__(self) -> None:
        self.recording = False
        self.session: str | None = None
        self.started: list[str] = []
        self.stopped = 0

    async def start(self, app: str) -> str:
        self.recording = True
        self.session = "s-auto"
        self.started.append(app)
        return self.session

    async def stop(self) -> None:
        self.recording = False
        self.stopped += 1


def _watcher(capture: _Capture, clock: _Clock, bus: EventBus) -> MeetingWatcher:
    return MeetingWatcher(
        probe=_Probe(),
        bus=bus,
        get_mode=None,  # type: ignore[arg-type]
        is_recording=lambda: capture.recording,
        current_session=lambda: capture.session,
        start_capture=capture.start,
        stop_capture=capture.stop,
        clock=clock,
    )


async def _drain(queue) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_ask_mode_announces_after_debounce_and_ends() -> None:
    bus, clock, capture = EventBus(), _Clock(), _Capture()
    queue = await bus.subscribe()
    watcher = _watcher(capture, clock, bus)
    zoom = [_User("zoom.exe", "Zoom", True)]
    await watcher.tick(zoom, "ask")
    clock.now = START_AFTER_S - 0.5
    await watcher.tick(zoom, "ask")
    assert await _drain(queue) == []
    clock.now = START_AFTER_S + 0.1
    await watcher.tick(zoom, "ask")
    detected = await _drain(queue)
    assert detected[0]["status"] == "detected" and detected[0]["app"] == "Zoom"
    assert capture.started == []

    await watcher.tick([], "ask")
    clock.now += END_AFTER_S + 0.1
    await watcher.tick([], "ask")
    ended = await _drain(queue)
    assert ended[-1]["status"] == "ended" and ended[-1]["auto_stopped"] is False
    assert watcher.state.active is False


@pytest.mark.asyncio
async def test_auto_mode_starts_and_stops_its_own_recording() -> None:
    bus, clock, capture = EventBus(), _Clock(), _Capture()
    watcher = _watcher(capture, clock, bus)
    teams = [_User("MSTeams", "Microsoft Teams", True), _User("chrome.exe", "Google Chrome", True, True)]
    await watcher.tick(teams, "auto")
    clock.now = START_AFTER_S + 1
    await watcher.tick(teams, "auto")
    assert capture.started == ["Microsoft Teams"]
    assert watcher.state.auto_session_id == "s-auto"
    await watcher.tick([], "auto")
    clock.now += END_AFTER_S + 1
    await watcher.tick([], "auto")
    assert capture.stopped == 1


@pytest.mark.asyncio
async def test_auto_mode_never_stops_a_recording_it_did_not_start() -> None:
    bus, clock, capture = EventBus(), _Clock(), _Capture()
    capture.recording, capture.session = True, "s-manual"
    watcher = _watcher(capture, clock, bus)
    zoom = [_User("zoom.exe", "Zoom", True)]
    await watcher.tick(zoom, "auto")
    clock.now = START_AFTER_S + 1
    await watcher.tick(zoom, "auto")
    assert capture.started == []
    await watcher.tick([], "auto")
    clock.now += END_AFTER_S + 1
    await watcher.tick([], "auto")
    assert capture.stopped == 0


def test_mode_normalization() -> None:
    assert normalize_mode("AUTO") == "auto"
    assert normalize_mode(None) == "ask"
    assert normalize_mode("talvez") == "ask"


# ------------------------------------------------------- notas e templates


class _PromptLlm:
    def __init__(self) -> None:
        self.prompt = ""

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        self.prompt = prompt
        return (
            '{"language":"pt","overview":"Ok.","topics":[{"title":"Dor e problema principal","points":["Lento"]}],'
            '"decisions":[],"action_items":[],"open_items":[],'
            '"user_notes":[{"note":"preço caro","context":"O cliente achou o plano anual caro."}]}'
        )


@pytest.mark.asyncio
async def test_summary_uses_template_and_user_notes(tmp_path) -> None:
    store = SqliteStore(tmp_path / "n.db")
    await store.initialize()
    await TemplateService(store).ensure_builtins()
    session = Session(id=new_id(), title="Call", started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(id=new_id(), session_id=session.id, start_ms=60_000, end_ms=62_000, text="Achei caro o anual.")
    )
    await store.add_user_note(UserNote(id=new_id(), session_id=session.id, at_ms=61_000, text="preço caro", created_at=datetime.now(tz=UTC)))
    llm = _PromptLlm()
    summary = await SummarizeService(llm, store).summarize(session.id, "tpl-sales")
    assert "Objeções levantadas" in llm.prompt
    assert "[01:01] preço caro" in llm.prompt
    assert "## Suas anotações" in summary.notes_markdown
    assert "**preço caro** — O cliente achou o plano anual caro." in summary.notes_markdown
    stored = await store.get_session(session.id)
    assert stored is not None and stored.template_id == "tpl-sales"


def test_parse_user_notes_accepts_strings_and_objects() -> None:
    parsed = parse_summary_json('{"user_notes": ["a", {"note": "b", "context": "c"}, {"context": "sem nota"}]}')
    assert parsed["user_notes"] == [{"note": "a", "context": ""}, {"note": "b", "context": "c"}]
    assert "- **a**" in summary_to_markdown("T", parsed)


def test_builtins_have_unique_ids_and_kinds() -> None:
    ids = [item.id for item in BUILTINS]
    assert len(ids) == len(set(ids))
    assert {item.kind for item in BUILTINS} == {"note", "recipe"}


@pytest.mark.asyncio
async def test_notes_and_templates_endpoints(client: AsyncClient, app) -> None:
    store = app.state.container.store
    await TemplateService(store).ensure_builtins()
    session = Session(id=new_id(), title="S", started_at=datetime.now(tz=UTC), ended_at=None, status="recording")
    await store.create_session(session)

    created = await client.post(f"/sessions/{session.id}/notes", headers=auth(), json={"text": "  revisar contrato "})
    assert created.status_code == 201
    note = created.json()
    assert note["text"] == "revisar contrato" and note["at_ms"] >= 0
    timed = await client.post(f"/sessions/{session.id}/notes", headers=auth(), json={"text": "início", "at_ms": 0})
    listed = await client.get(f"/sessions/{session.id}/notes", headers=auth())
    assert [item["text"] for item in listed.json()] == ["início", "revisar contrato"]
    edited = await client.patch(f"/sessions/{session.id}/notes/{note['id']}", headers=auth(), json={"text": "revisar"})
    assert any(item["text"] == "revisar" for item in edited.json())
    gone = await client.delete(f"/sessions/{session.id}/notes/{timed.json()['id']}", headers=auth())
    assert gone.status_code == 204

    recipes = await client.get("/templates?kind=recipe", headers=auth())
    assert recipes.status_code == 200 and all(item["kind"] == "recipe" for item in recipes.json())
    mine = await client.post("/templates", headers=auth(), json={"kind": "note", "name": "Board", "body": "Números\nRiscos"})
    assert mine.status_code == 201 and mine.json()["builtin"] is False
    locked = await client.delete("/templates/tpl-sales", headers=auth())
    assert locked.status_code == 409
    renamed = await client.patch(f"/templates/{mine.json()['id']}", headers=auth(), json={"name": "Conselho"})
    assert renamed.json()["name"] == "Conselho"
    removed = await client.delete(f"/templates/{mine.json()['id']}", headers=auth())
    assert removed.status_code == 204
