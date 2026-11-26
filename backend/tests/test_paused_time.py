from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.domain.models import Session
from app.schemas.api import SessionOut
from tests.conftest import auth


@pytest.mark.asyncio
async def test_paused_time_accumulates_and_is_stored_on_stop(client: AsyncClient, app) -> None:
    capture = app.state.container.capture
    wall = {"now": datetime(2026, 11, 26, 10, 0, tzinfo=UTC)}
    capture._wall = lambda: wall["now"]
    started = await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    session_id = started.json()["session_id"]

    paused = (await client.post("/capture/pause", headers=auth())).json()
    assert paused["paused_ms"] == 0
    assert paused["paused_at"]
    wall["now"] += timedelta(seconds=30)
    resumed = (await client.post("/capture/resume", headers=auth())).json()
    assert resumed["paused_ms"] == 30_000
    assert resumed["paused_at"] is None

    # Running time does not count; a second pause adds up, and stop while paused closes it.
    wall["now"] += timedelta(seconds=100)
    await client.post("/capture/pause", headers=auth())
    wall["now"] += timedelta(seconds=5)
    state = (await client.get("/capture/state", headers=auth())).json()
    assert state["paused_ms"] == 30_000 and state["paused_at"]
    await client.post("/capture/stop", headers=auth())

    session = await app.state.container.store.get_session(session_id)
    assert session.paused_ms == 35_000


@pytest.mark.asyncio
async def test_auto_pause_counts_as_paused(client: AsyncClient, app) -> None:
    from tests.test_capture import _Clock

    capture = app.state.container.capture
    wall = {"now": datetime(2026, 11, 26, 10, 0, tzinfo=UTC)}
    capture._wall = lambda: wall["now"]
    clock = _Clock()
    capture._clock = clock
    await client.post("/capture/start", headers=auth(), json={"mic_only": True})
    clock.now += 300
    await capture.idle_tick()
    clock.now += 120
    await capture.idle_tick()
    assert capture.state.paused is True
    wall["now"] += timedelta(seconds=12)
    await capture.resume()
    assert capture.state.paused_ms == 12_000


def test_session_duration_discounts_paused_time() -> None:
    start = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)
    base = Session(id="s", title="t", started_at=start, ended_at=start + timedelta(minutes=10), status="stopped")
    assert SessionOut.from_domain(base).duration_ms == 600_000
    paused = Session(**{**base.__dict__, "paused_ms": 120_000})
    assert SessionOut.from_domain(paused).duration_ms == 480_000
