from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.setup import UNATTENDED_FILE
from app.schemas.api import BootstrapIn


@pytest.mark.asyncio
async def test_unattended_marker_starts_local_bootstrap_once(app, settings) -> None:
    setup = app.state.container.setup
    store = app.state.container.store
    started: list[BootstrapIn] = []

    async def fake_bootstrap(payload: BootstrapIn | None = None) -> None:
        assert payload is not None
        started.append(payload)

    setup.start_bootstrap = fake_bootstrap
    marker: Path = settings.data_dir / UNATTENDED_FILE
    marker.write_text(json.dumps({"provider": "neste_pc", "agent": "claude-code", "language": "pt"}), encoding="utf-8")

    assert await setup.apply_unattended() is True
    assert not marker.exists(), "the marker is consumed on first start"
    assert len(started) == 1
    payload = started[0]
    assert payload.provider == "neste_pc"
    assert payload.ollama_model and payload.whisper_model
    assert payload.save_recordings is True
    assert await store.get_setting("disclaimer_accepted") == "1"
    assert await store.get_setting("disclaimer_kind") == "local"
    assert await store.get_setting("unattended_source") == "claude-code"

    # Second start: no marker, nothing happens.
    assert await setup.apply_unattended() is False
    assert len(started) == 1


@pytest.mark.asyncio
async def test_unattended_marker_ignored_when_already_set_up(app, settings) -> None:
    setup = app.state.container.setup
    store = app.state.container.store
    await store.set_setting("setup_complete", "1")
    called = False

    async def fake_bootstrap(payload: BootstrapIn | None = None) -> None:
        nonlocal called
        called = True

    setup.start_bootstrap = fake_bootstrap
    marker: Path = settings.data_dir / UNATTENDED_FILE
    marker.write_text("{}", encoding="utf-8")

    assert await setup.apply_unattended() is False
    assert not marker.exists()
    assert called is False
    assert await store.get_setting("disclaimer_accepted") != "1"


@pytest.mark.asyncio
async def test_unattended_marker_tolerates_garbage(app, settings) -> None:
    setup = app.state.container.setup
    started = 0

    async def fake_bootstrap(payload: BootstrapIn | None = None) -> None:
        nonlocal started
        started += 1

    setup.start_bootstrap = fake_bootstrap
    (settings.data_dir / UNATTENDED_FILE).write_text("not json", encoding="utf-8")
    assert await setup.apply_unattended() is True
    assert started == 1


@pytest.mark.asyncio
async def test_no_marker_is_a_noop(app) -> None:
    assert await app.state.container.setup.apply_unattended() is False
