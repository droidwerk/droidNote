from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from httpx import AsyncClient

from app.application.brief import BriefService, match_people, title_similarity, title_tokens
from app.application.retention import RetentionService
from app.application.tasks import TaskService
from app.domain.models import ActionItem, Session, Summary, TranscriptSegment
from app.infrastructure.audio.agc import TARGET_RMS, AutoGain
from app.infrastructure.calendar.ics import CalendarError, expand, normalize_url, parse_events
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth


async def _store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    return store


async def _session(store: SqliteStore, title: str, *, days_ago: float = 0, status: str = "stopped") -> Session:
    started = datetime.now(tz=UTC) - timedelta(days=days_ago)
    session = Session(
        id=new_id(),
        title=title,
        started_at=started,
        ended_at=started + timedelta(minutes=30) if status == "stopped" else None,
        status=status,  # type: ignore[arg-type]
    )
    await store.create_session(session)
    return session


async def _summary(store: SqliteStore, session_id: str, *, decisions: list[str], actions: list[str]) -> None:
    await store.save_summary(
        Summary(
            id=new_id(),
            session_id=session_id,
            highlights=[],
            decisions=decisions,
            action_items=[ActionItem(text=item, owner="Ana") for item in actions],
            raw_text="{}",
            created_at=datetime.now(tz=UTC),
        )
    )


# ------------------------------------------------------------- tarefas


async def test_task_sync_keeps_done_state_across_regenerated_notes(tmp_path) -> None:
    store = await _store(tmp_path)
    tasks = TaskService(store)
    session = await _session(store, "Daily")
    first = await tasks.sync_from_summary(
        session.id, [ActionItem("Enviar proposta", "Ana"), ActionItem("Revisar contrato"), ActionItem("Ligar p/ Bia")]
    )
    by_text = {item.text: item for item in first}
    await tasks.update(by_text["Enviar proposta"].id, done=True)
    await tasks.update(by_text["Ligar p/ Bia"].id, done=True)

    # Ata nova: "enviar proposta" com outra caixa, "revisar" sumiu, "ligar" (feita) sumiu.
    second = await tasks.sync_from_summary(session.id, [ActionItem("Enviar  PROPOSTA!", "Ana"), ActionItem("Agendar demo")])
    texts = {item.text: item for item in second}
    assert texts["Enviar  PROPOSTA!"].id == by_text["Enviar proposta"].id
    assert texts["Enviar  PROPOSTA!"].done is True
    assert "Revisar contrato" not in texts  # aberta e fora da ata nova: sai
    assert texts["Ligar p/ Bia"].done is True  # feita: fica como histórico
    assert "Agendar demo" in texts


async def test_note_task_and_ai_task_do_not_duplicate(tmp_path) -> None:
    store = await _store(tmp_path)
    tasks = TaskService(store)
    session = await _session(store, "Kickoff")
    other = await _session(store, "Outra")

    # A ata criou a tarefa; depois "Virar tarefa" na anotação igual devolve a mesma.
    (ai_task,) = await tasks.sync_from_summary(session.id, [ActionItem("Enviar proposta revisada até sexta")])
    again = await tasks.create("enviar proposta revisada ate sexta", session_id=session.id)
    assert again.id == ai_task.id
    assert len(await tasks.list(session_id=session.id)) == 1
    # Em outra conversa é outra tarefa.
    assert (await tasks.create("Enviar proposta revisada até sexta", session_id=other.id)).id != ai_task.id

    # Ordem inversa: a anotação virou tarefa antes; a ata (re)gerada não repete.
    third = await _session(store, "Terceira")
    manual = await tasks.create("Mandar contrato", session_id=third.id)
    synced = await tasks.sync_from_summary(third.id, [ActionItem("Mandar contrato!"), ActionItem("Agendar demo")])
    assert sorted(item.text for item in synced) == ["Agendar demo", "Mandar contrato"]
    assert manual.id in {item.id for item in synced}


async def test_search_covers_notes_minutes_and_tasks(tmp_path) -> None:
    from app.application.search import search_extras
    from app.domain.models import UserNote

    store = await _store(tmp_path)
    session = await _session(store, "Kickoff")
    await store.add_user_note(
        UserNote(id=new_id(), session_id=session.id, at_ms=29_000, text="Revisar o ORÇAMENTO", created_at=datetime.now(tz=UTC), kind="task")
    )
    await _summary(store, session.id, decisions=[], actions=[])
    await store.save_summary_notes(session.id, "# Kickoff\n\n## Decisões\n\n- Orçamento aprovado `01:10`\n")
    await TaskService(store).create("Mandar orçamento final", session_id=session.id)

    hits = await search_extras(store, "orcamento")
    assert [(item.text, item.at_ms, item.kind) for item in hits.notes] == [("Revisar o ORÇAMENTO", 29_000, "task")]
    assert [(item.session_id, item.excerpt) for item in hits.summaries] == [(session.id, "Orçamento aprovado 01:10")]
    assert [item.text for item in hits.tasks] == ["Mandar orçamento final"]
    assert (await search_extras(store, "o")).notes == []  # termo curto demais
    assert (await search_extras(store, "inexistente")).tasks == []


async def test_search_endpoint_returns_extra_groups(client: AsyncClient) -> None:
    await client.post("/tasks", headers=auth(), json={"text": "Ligar para a Bia"})
    body = (await client.get("/sessions/search", headers=auth(), params={"q": "bia"})).json()
    assert [item["text"] for item in body["tasks"]] == ["Ligar para a Bia"]
    assert body["notes"] == [] and body["summaries"] == [] and body["segments"] == []


async def test_task_backfill_runs_once(tmp_path) -> None:
    store = await _store(tmp_path)
    session = await _session(store, "Antiga")
    await _summary(store, session.id, decisions=[], actions=["Mandar ata"])
    tasks = TaskService(store)
    assert await tasks.backfill() == 1
    assert [item.text for item in await tasks.list()] == ["Mandar ata"]
    await store.delete_task((await tasks.list())[0].id)
    assert await tasks.backfill() == 0
    assert await tasks.list() == []


async def test_tasks_endpoints(client: AsyncClient) -> None:
    created = await client.post("/tasks", headers=auth(), json={"text": "Comprar café", "owner": "Eu"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["origin"] == "manual"
    done = await client.patch(f"/tasks/{task_id}", headers=auth(), json={"done": True})
    assert done.json()["done"] is True and done.json()["done_at"]
    cleared = await client.patch(f"/tasks/{task_id}", headers=auth(), json={"owner": None})
    assert cleared.json()["owner"] is None
    assert cleared.json()["text"] == "Comprar café"
    assert (await client.get("/tasks?status=open", headers=auth())).json() == []
    assert len((await client.get("/tasks?status=done", headers=auth())).json()) == 1
    assert (await client.delete(f"/tasks/{task_id}", headers=auth())).status_code == 204
    assert (await client.delete(f"/tasks/{task_id}", headers=auth())).status_code == 404


# ------------------------------------------------------------- calendário

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:weekly-1
SUMMARY:1:1 Ana
DTSTART;TZID=America/Sao_Paulo:20261026T100000
DTEND;TZID=America/Sao_Paulo:20261026T103000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261231T235959Z
EXDATE;TZID=America/Sao_Paulo:20261028T100000
ATTENDEE;CN="Ana Souza";ROLE=REQ-PARTICIPANT:mailto:ana@example.com
ATTENDEE:mailto:bruno.lima@example.com
BEGIN:VALARM
TRIGGER:-PT10M
ACTION:DISPLAY
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:weekly-1
RECURRENCE-ID;TZID=America/Sao_Paulo:20261102T100000
SUMMARY:1:1 Ana (remarcada)
DTSTART;TZID=America/Sao_Paulo:20261102T150000
DTEND;TZID=America/Sao_Paulo:20261102T153000
END:VEVENT
BEGIN:VEVENT
UID:once
SUMMARY:Kickoff projeto Atlas com cliente\\, parte 1
DTSTART:20261029T170000Z
DURATION:PT1H
LOCATION:https://meet.example.com/x
END:VEVENT
BEGIN:VEVENT
UID:cancelled
SUMMARY:Cancelada
STATUS:CANCELLED
DTSTART:20261029T120000Z
DTEND:20261029T130000Z
END:VEVENT
BEGIN:VEVENT
UID:allday
SUMMARY:Feriado
DTSTART;VALUE=DATE:20261030
END:VEVENT
END:VCALENDAR
"""


def test_ics_rejects_private_address() -> None:
    assert normalize_url("webcal://calendar.example.com/basic.ics").startswith("https://")
    for raw in ("http://127.0.0.1/a.ics", "http://10.1.2.3/a.ics", "http://169.254.169.254/a.ics"):
        try:
            normalize_url(raw)
        except CalendarError as exc:
            assert str(exc) == "blocked_url"
        else:
            raise AssertionError(raw)


def test_ics_expands_recurrence_overrides_and_skips_noise() -> None:
    folded = ICS.replace("SUMMARY:Kickoff projeto Atlas", "SUMMARY:Kickoff projeto\r\n  Atlas")
    events = expand(
        parse_events(folded),
        datetime(2026, 10, 26, tzinfo=UTC),
        datetime(2026, 11, 5, tzinfo=UTC),
    )
    titles = [(event.title, event.start.isoformat()) for event in events]
    assert titles == [
        ("1:1 Ana", "2026-10-26T13:00:00+00:00"),
        ("Kickoff projeto Atlas com cliente, parte 1", "2026-10-29T17:00:00+00:00"),
        ("1:1 Ana (remarcada)", "2026-11-02T18:00:00+00:00"),
        ("1:1 Ana", "2026-11-04T13:00:00+00:00"),
    ]
    first = events[0]
    assert first.end - first.start == timedelta(minutes=30)
    assert [item.name for item in first.attendees] == ["Ana Souza", "bruno.lima"]
    assert events[1].location == "https://meet.example.com/x"


# ------------------------------------------------------------- briefing


def test_title_tokens_ignore_dates_apps_and_filler() -> None:
    assert title_tokens("Zoom · 28/10/2026 14:00") == set()
    assert title_tokens("Daily do time de dados") == {"daily", "time", "dados"}
    assert title_similarity("Daily time de dados · 27/10", "daily — Time de Dados") == 1.0
    assert title_similarity("Kickoff Atlas", "Retro Atlas") < 0.5


def test_match_people_by_full_or_unique_first_name() -> None:
    known = {"p1": "Ana Souza", "p2": "Bruno Lima", "p3": "Bruno Alves"}
    assert match_people(["ana souza", "ana.souza", "bruno"], known) == {"p1"}


async def test_brief_finds_same_title_and_one_on_one(tmp_path) -> None:
    store = await _store(tmp_path)
    ana = await store.create_person("Ana Souza")
    older = await _session(store, "Daily dados · 20/10", days_ago=8)
    recent = await _session(store, "Daily dados · 27/10", days_ago=1)
    one_on_one = await _session(store, "Conversa", days_ago=3)
    await _session(store, "Zoom · 26/10/2026", days_ago=2)
    await store.set_session_participants(one_on_one.id, [ana.id])
    await _summary(store, recent.id, decisions=["Migrar para Postgres"], actions=["Criar tabela"])
    await TaskService(store).sync_from_summary(recent.id, [ActionItem("Criar tabela")])

    # Gravação de hoje sem ata: é a mais recente, mas não deve virar "reunião anterior".
    empty = await _session(store, "Daily dados · 28/10", days_ago=0.1)
    brief = await BriefService(store).for_title("Daily Dados", [])
    assert [item.session.id for item in brief.related] == [recent.id, empty.id, older.id]
    assert brief.related[0].decisions == ["Migrar para Postgres"]
    assert [task.text for task in brief.pending] == ["Criar tabela"]

    by_person = await BriefService(store).for_title("Papo semanal", ["Ana Souza"])
    assert [item.session.id for item in by_person.related] == [one_on_one.id]
    assert by_person.related[0].reason == "people"

    # Só a Ana está cadastrada, mas o convite tem duas pessoas: não é 1:1 com ela.
    group = await BriefService(store).for_title("Papo semanal", ["Ana Souza", "Rafael Dias"])
    assert group.related == []

    nothing = await BriefService(store).for_title("Zoom · 28/10", [])
    assert nothing.related == []


async def test_brief_endpoint_for_session_excludes_itself(client: AsyncClient, app) -> None:
    store = app.state.container.store
    before = await _session(store, "Planejamento Q4", days_ago=7)
    current = await _session(store, "Planejamento Q4")
    response = await client.get(f"/brief?session_id={current.id}", headers=auth())
    assert response.status_code == 200
    assert [item["session_id"] for item in response.json()["related"]] == [before.id]
    empty = await client.get("/calendar/upcoming", headers=auth())
    assert empty.json() == {"configured": False, "error": None, "events": []}


# ------------------------------------------------------------- retenção


async def test_retention_deletes_old_audio_and_transcripts_only(tmp_path) -> None:
    store = await _store(tmp_path)
    folder = tmp_path / "rec"
    folder.mkdir()
    old = await _session(store, "Velha", days_ago=40)
    fresh = await _session(store, "Nova", days_ago=2)
    live = await _session(store, "Ao vivo", days_ago=60, status="recording")
    for session in (old, fresh, live):
        (folder / f"{session.id}.wav").write_bytes(b"RIFF")
        await store.add_segment(
            TranscriptSegment(id=new_id(), session_id=session.id, start_ms=0, end_ms=900, text="oi")
        )
    await _summary(store, old.id, decisions=["Fica"], actions=[])
    service = RetentionService(store, lambda session_id: folder / f"{session_id}.wav")

    preview = await service.run(dry_run=True, audio_days=30, transcript_days=30)
    assert (preview.audio_files, preview.transcripts) == (1, 1)
    assert (folder / f"{old.id}.wav").exists()

    await store.set_setting("retention_audio_days", "30")
    await store.set_setting("retention_transcript_days", "30")
    report = await service.run()
    assert (report.audio_files, report.transcripts) == (1, 1)
    assert not (folder / f"{old.id}.wav").exists()
    assert (folder / f"{fresh.id}.wav").exists() and (folder / f"{live.id}.wav").exists()
    assert await store.list_segments(old.id) == []
    assert len(await store.list_segments(fresh.id)) == 1
    assert (await store.get_summary(old.id)).decisions == ["Fica"]
    assert (await store.get_session(old.id)).transcript_purged_at is not None
    again = await service.run()
    assert (again.audio_files, again.transcripts) == (0, 0)


async def test_settings_hide_calendar_url_and_store_phase2_options(client: AsyncClient) -> None:
    bad = await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": "ftp://x"})
    assert bad.status_code == 400
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={
            "calendar_ics_url": "webcal://calendar.example.com/private-abc/basic.ics",
            "consent_message": "Estou gravando para fazer a ata.",
            "retention_audio_days": 30,
            "retention_transcript_days": 0,
            "auto_gain": False,
        },
    )
    body = saved.json()
    assert body["has_calendar"] is True
    assert body["calendar_hint"] == "calendar.example.com"
    assert "private-abc" not in saved.text
    assert body["consent_message"] == "Estou gravando para fazer a ata."
    assert (body["retention_audio_days"], body["retention_transcript_days"], body["auto_gain"]) == (30, 0, False)
    preview = await client.get("/setup/retention/preview?audio_days=7", headers=auth())
    assert preview.json()["audio_days"] == 7


async def test_folder_rename(client: AsyncClient) -> None:
    first = (await client.post("/tags", headers=auth(), json={"name": "Clientes"})).json()
    await client.post("/tags", headers=auth(), json={"name": "Aulas"})
    renamed = await client.patch(f"/tags/{first['id']}", headers=auth(), json={"name": "Clientes 2026"})
    assert renamed.json()["name"] == "Clientes 2026"
    clash = await client.patch(f"/tags/{first['id']}", headers=auth(), json={"name": "aulas"})
    assert clash.status_code == 409
    missing = await client.patch("/tags/nope", headers=auth(), json={"name": "X"})
    assert missing.status_code == 404


# ------------------------------------------------------------- ganho


def _speech(level: float, seconds: float = 2.0) -> np.ndarray:
    t = np.arange(int(16000 * seconds)) / 16000
    return (level * np.sqrt(2) * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_auto_gain_lifts_quiet_mic_without_pumping_silence() -> None:
    agc = AutoGain()
    quiet = _speech(0.015)
    out = np.concatenate([agc.process(quiet[i : i + 1600]) for i in range(0, quiet.size, 1600)])
    tail = out[-8000:]
    level = float(np.sqrt(np.mean(tail * tail)))
    assert TARGET_RMS * 0.6 < level < TARGET_RMS * 1.4
    assert agc.gain_db > 10

    silence = AutoGain()
    hiss = np.random.default_rng(1).normal(0, 0.001, 32000).astype(np.float32)
    assert np.allclose(silence.process(hiss), hiss)

    loud = AutoGain()
    peak = loud.process(_speech(0.5))
    assert float(np.max(np.abs(peak))) <= 1.0

    off = AutoGain(enabled=False)
    assert np.array_equal(off.process(quiet), quiet)
