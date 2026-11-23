from __future__ import annotations

import pytest

from app.domain.models import SetupComponentStatus


def _stub_bootstrap(setup, llm_status: str = "ready") -> list[int]:
    runs: list[int] = []

    async def fake_bootstrap() -> None:
        runs.append(1)

    async def fake_status() -> SetupComponentStatus:
        return SetupComponentStatus(status=llm_status, progress=100, message="")

    setup._bootstrap = fake_bootstrap
    setup._llm.status_component = fake_status
    return runs


@pytest.mark.asyncio
async def test_start_bootstrap_marks_pending_and_success_clears_it(app) -> None:
    setup = app.state.container.setup
    store = app.state.container.store
    runs = _stub_bootstrap(setup)

    await setup.start_bootstrap()
    assert await store.get_setting("bootstrap_pending") == "1"
    await setup._task
    assert runs == [1]
    assert await store.get_setting("bootstrap_pending") == "0"
    assert await store.get_setting("setup_complete") == "1"


@pytest.mark.asyncio
async def test_failed_bootstrap_stays_pending(app) -> None:
    setup = app.state.container.setup
    store = app.state.container.store
    _stub_bootstrap(setup, llm_status="error")

    await setup.start_bootstrap()
    await setup._task
    assert await store.get_setting("bootstrap_pending") == "1"
    assert await store.get_setting("setup_complete") != "1"


@pytest.mark.asyncio
async def test_resume_starts_pending_bootstrap(app) -> None:
    setup = app.state.container.setup
    store = app.state.container.store
    runs = _stub_bootstrap(setup)
    await store.set_setting("bootstrap_pending", "1")

    assert await setup.resume_bootstrap() is True
    await setup._task
    assert runs == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize(("pending", "complete"), [("1", "1"), (None, None), ("0", None)])
async def test_resume_noop_when_complete_or_not_pending(app, pending, complete) -> None:
    setup = app.state.container.setup
    store = app.state.container.store
    runs = _stub_bootstrap(setup)
    if pending is not None:
        await store.set_setting("bootstrap_pending", pending)
    if complete is not None:
        await store.set_setting("setup_complete", complete)

    assert await setup.resume_bootstrap() is False
    assert setup._task is None
    assert runs == []


@pytest.mark.asyncio
async def test_unattended_marker_kept_if_bootstrap_start_crashes(app, settings) -> None:
    from app.application.setup import UNATTENDED_FILE

    setup = app.state.container.setup

    async def boom(payload=None) -> None:
        raise RuntimeError("crash")

    setup.start_bootstrap = boom
    marker = settings.data_dir / UNATTENDED_FILE
    marker.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError):
        await setup.apply_unattended()
    assert marker.exists(), "marker survives so the next start retries"
    assert await app.state.container.store.get_setting("disclaimer_accepted") != "1"
