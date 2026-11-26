from __future__ import annotations

import asyncio
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest

from app.application.calendar_watch import CalendarRecorder, migrate_auto_record
from app.infrastructure.calendar.ics import Attendee, CalendarEvent

T0 = datetime(2026, 11, 24, 19, 0, tzinfo=UTC)


def _event(uid: str = "a", start: datetime = T0, minutes: float = 60, title: str = "Planejamento") -> CalendarEvent:
    # Um convidado: agenda "de verdade", não só livre/ocupado.
    return CalendarEvent(
        uid=uid, title=title, start=start, end=start + timedelta(minutes=minutes), attendees=(Attendee("Ana"),)
    )


class _Store:
    def __init__(self, **settings: str) -> None:
        self.settings = {"calendar_ics_url": "https://example.test/cal.ics", **settings}

    async def get_setting(self, key: str) -> str | None:
        return self.settings.get(key)

    async def set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value

    async def get_session(self, session_id: str):
        return SimpleNamespace(title=f"Reunião {session_id}")


class _Calendar:
    def __init__(self, events: list[CalendarEvent]) -> None:
        self.events = events
        self.calls = 0

    async def upcoming(self, url: str, **_: object) -> list[CalendarEvent]:
        self.calls += 1
        return self.events


class _Bus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)


def _recorder(events=None, **settings: str):
    started: list[tuple[str, datetime]] = []
    state = {"recording": False, "ready": True, "now": 0.0, "since": None, "until": None}

    async def start(title: str, planned_end: datetime) -> str:
        started.append((title, planned_end))
        return f"s{len(started)}"

    bus = _Bus()
    calendar = _Calendar(events or [])
    rec = CalendarRecorder(
        _Store(**settings),  # type: ignore[arg-type]
        calendar,  # type: ignore[arg-type]
        bus,  # type: ignore[arg-type]
        is_recording=lambda: state["recording"],
        asr_ready=lambda: state["ready"],
        start_capture=start,
        live_span=lambda: (state["since"], state["until"]),
        clock=lambda: state["now"],
    )
    return rec, started, state, bus, calendar


@pytest.mark.asyncio
async def test_fires_once_inside_window_with_event_end() -> None:
    rec, started, _, bus, _ = _recorder()
    events = [_event()]
    assert await rec.tick(events, T0 - timedelta(seconds=31)) is None
    assert await rec.tick(events, T0 - timedelta(seconds=20)) == "s1"
    assert started == [("Planejamento", T0 + timedelta(minutes=60))]
    assert bus.events == [{"type": "calendar", "status": "auto-started", "session_id": "s1", "title": "Planejamento"}]
    # Mesmo uid@start não grava de novo (ex.: o usuário parou na mão).
    assert await rec.tick(events, T0 + timedelta(minutes=2)) is None
    assert len(started) == 1


@pytest.mark.asyncio
async def test_skips_recording_asr_not_ready_late_and_long_events() -> None:
    rec, started, state, _, _ = _recorder()
    state["recording"] = True
    assert await rec.tick([_event()], T0) is None
    state["recording"], state["ready"] = False, False
    assert await rec.tick([_event()], T0) is None
    state["ready"] = True
    assert await rec.tick([_event()], T0 + timedelta(minutes=10, seconds=1)) is None
    assert await rec.tick([_event(minutes=20 * 60)], T0) is None
    assert started == []


@pytest.mark.asyncio
async def test_back_to_back_next_event_fires_after_stop() -> None:
    rec, started, state, _, _ = _recorder()
    events = [_event("a"), _event("b", start=T0 + timedelta(hours=1))]
    assert await rec.tick(events, T0) == "s1"
    state["recording"] = True
    assert await rec.tick(events, T0 + timedelta(hours=1)) is None
    # A gravação A parou (fim do evento sem resposta): B entra no próximo tick.
    state["recording"] = False
    assert await rec.tick(events, T0 + timedelta(hours=1, minutes=2, seconds=30)) == "s2"
    assert [item[0] for item in started] == ["Planejamento", "Planejamento"]


@pytest.mark.asyncio
async def test_busy_only_calendar_and_untitled_event_never_auto_start() -> None:
    rec, started, _, _, _ = _recorder()
    busy = [CalendarEvent(uid="x", title="Ocupado", start=T0, end=T0 + timedelta(hours=1))]
    assert await rec.tick(busy, T0) is None
    assert await rec.tick([_event(title="  ")], T0) is None
    assert started == []


@pytest.mark.asyncio
async def test_busy_only_skipped_when_setting_off() -> None:
    rec, started, _, _, _ = _recorder(calendar_record_busy="0")
    busy = [CalendarEvent(uid="x", title="Ocupado", start=T0, end=T0 + timedelta(hours=1))]
    assert await rec.tick(busy, T0) is None
    assert started == []


@pytest.mark.asyncio
async def test_busy_only_records_with_default_title_when_setting_on() -> None:
    rec, started, _, bus, _ = _recorder(calendar_record_busy="1")
    busy = [
        CalendarEvent(uid="x", title="Ocupado", start=T0, end=T0 + timedelta(hours=1)),
        CalendarEvent(uid="y", title="", start=T0 + timedelta(hours=3), end=T0 + timedelta(hours=4)),
    ]
    assert await rec.tick(busy, T0) == "s1"
    # Bloco sem título também grava: o título vem do padrão do CaptureService.
    assert await rec.tick(busy, T0 + timedelta(hours=3)) == "s2"
    assert [item[0] for item in started] == ["", ""]
    # O aviso mostra o título que a sessão ganhou, nunca "Gravação automática: " vazio.
    assert [event["title"] for event in bus.events] == ["Reunião s1", "Reunião s2"]
    # Agenda com detalhes continua sem gravar evento sem título.
    assert await rec.tick([_event("z", title=" ", start=T0 + timedelta(hours=5))], T0 + timedelta(hours=5)) is None


@pytest.mark.asyncio
async def test_manual_recording_covers_event_after_stop() -> None:
    rec, started, state, _, _ = _recorder()
    events = [_event("a"), _event("b", start=T0 + timedelta(hours=2))]
    # Botão "Gravar" do painel: planned_end = fim do evento, começou antes da janela.
    state.update(recording=True, since=T0 - timedelta(minutes=5), until=events[0].end)
    assert await rec.tick(events, T0) is None
    state.update(recording=False, since=None, until=None)
    assert await rec.tick(events, T0 + timedelta(minutes=3)) is None
    # Início comum (sem planned_end) dentro do evento também cobre.
    state.update(recording=True, since=T0 + timedelta(hours=2, minutes=1))
    assert await rec.tick(events, T0 + timedelta(hours=2, minutes=1)) is None
    state.update(recording=False, since=None)
    assert await rec.tick(events, T0 + timedelta(hours=2, minutes=3)) is None
    assert started == []


@pytest.mark.asyncio
async def test_upgrade_with_calendar_keeps_auto_record_off_and_offers() -> None:
    store = _Store()
    await migrate_auto_record(store)  # type: ignore[arg-type]
    assert store.settings["calendar_auto_record"] == "0"
    assert store.settings["calendar_auto_record_offer"] == "1"
    rec, started, _, _, calendar = _recorder([_event()], **store.settings)
    assert await rec._load() == []
    assert calendar.calls == 0
    # Já decidido (ou sem agenda): a migração não mexe.
    chosen = _Store(calendar_auto_record="1")
    await migrate_auto_record(chosen)  # type: ignore[arg-type]
    assert chosen.settings == {"calendar_ics_url": "https://example.test/cal.ics", "calendar_auto_record": "1"}
    empty = _Store(calendar_ics_url="")
    await migrate_auto_record(empty)  # type: ignore[arg-type]
    assert "calendar_auto_record" not in empty.settings


@pytest.mark.asyncio
async def test_load_respects_setting_and_caches_fetch() -> None:
    rec, _, state, _, calendar = _recorder([_event()], calendar_auto_record="0")
    assert await rec._load() == []
    assert calendar.calls == 0
    rec._store.settings["calendar_auto_record"] = "1"  # type: ignore[attr-defined]
    assert len(await rec._load()) == 1
    state["now"] = 299.0
    await rec._load()
    assert calendar.calls == 1
    state["now"] = 300.0
    await rec._load()
    assert calendar.calls == 2


@pytest.mark.asyncio
async def test_default_on_without_setting_and_close() -> None:
    rec, _, _, _, calendar = _recorder([_event()])
    assert len(await rec._load()) == 1
    rec.start()
    await asyncio.sleep(0)
    await rec.close()
    assert calendar.calls >= 1


@pytest.mark.asyncio
async def test_settings_first_connect_saves_on_and_offer_clears(client, app) -> None:
    from tests.conftest import auth

    store = app.state.container.store
    url = "https://example.test/cal.ics"
    saved = await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": url})
    assert saved.status_code == 200
    assert await store.get_setting("calendar_auto_record") == "1"
    assert saved.json()["calendar_auto_record_offer"] is False
    # Simula quem atualizou com agenda conectada.
    await store.set_setting("calendar_auto_record_offer", "1")
    got = await client.get("/setup/settings", headers=auth())
    assert got.json()["calendar_auto_record_offer"] is True
    answered = await client.put("/setup/settings", headers=auth(), json={"calendar_auto_record": True})
    assert answered.json()["calendar_auto_record_offer"] is False
    assert (await client.get("/setup/settings")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_settings_record_busy_default_off_and_round_trip(client, app) -> None:
    from tests.conftest import auth

    store = app.state.container.store
    # Conectar a agenda não liga o modo "Ocupado".
    saved = await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": "https://example.test/cal.ics"})
    assert saved.json()["calendar_record_busy"] is False
    assert await store.get_setting("calendar_record_busy") is None
    on = await client.put("/setup/settings", headers=auth(), json={"calendar_record_busy": True})
    assert on.json()["calendar_record_busy"] is True
    assert await store.get_setting("calendar_record_busy") == "1"
    off = await client.put("/setup/settings", headers=auth(), json={"calendar_record_busy": False})
    assert off.json()["calendar_record_busy"] is False
    bad = await client.put("/setup/settings", headers=auth(), json={"calendar_record_busy": "talvez"})
    assert bad.status_code == 422
    assert (await client.put("/setup/settings", json={"calendar_record_busy": True})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_replacing_or_disconnecting_calendar_turns_busy_off(client, app) -> None:
    from tests.conftest import auth

    store = app.state.container.store
    url = "https://example.test/cal.ics"
    await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": url, "calendar_record_busy": True})
    # Salvar a mesma agenda de novo mantém a escolha.
    same = await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": url})
    assert same.json()["calendar_record_busy"] is True
    swapped = await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": "https://example.test/other.ics"})
    assert swapped.json()["calendar_record_busy"] is False
    assert (await client.get("/setup/settings", headers=auth())).json()["calendar_record_busy"] is False
    rec, started, _, _, _ = _recorder(calendar_record_busy=(await store.get_setting("calendar_record_busy")) or "")
    busy = [CalendarEvent(uid="x", title="Ocupado", start=T0, end=T0 + timedelta(hours=1))]
    assert await rec.tick(busy, T0) is None
    assert started == []
    await client.put("/setup/settings", headers=auth(), json={"calendar_record_busy": True})
    gone = await client.put("/setup/settings", headers=auth(), json={"calendar_ics_url": ""})
    assert gone.json()["calendar_record_busy"] is False

