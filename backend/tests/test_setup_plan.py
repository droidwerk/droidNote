from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import auth


@pytest.mark.asyncio
async def test_setup_plan_exposes_ram_and_suggestions(client: AsyncClient) -> None:
    response = await client.get("/setup/plan", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert "suggested_note_model" in body
    assert "suggested_whisper_model" in body
    assert "ram_gb" in body
    assert isinstance(body["ollama"], list)
    assert isinstance(body["whisper"], list)
    assert "free_disk_gb" in body
    assert "disk_ok" in body
    status = await client.get("/setup/status", headers=auth())
    assert status.status_code == 200
    assert "setup_complete" in status.json()


@pytest.mark.asyncio
async def test_diagnostics_zip_endpoint(client: AsyncClient) -> None:
    response = await client.get("/setup/diagnostics", headers=auth())
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_bootstrap_without_body_still_works(client: AsyncClient) -> None:
    response = await client.post("/setup/bootstrap", headers=auth())
    assert response.status_code == 200
    assert "whisper" in response.json()


@pytest.mark.asyncio
async def test_disclaimer_stores_kind(client: AsyncClient) -> None:
    response = await client.post(
        "/setup/disclaimer",
        headers=auth(),
        json={"accepted": True, "kind": "openai"},
    )
    assert response.status_code == 200
    assert response.json()["disclaimer_kind"] == "openai"


@pytest.mark.asyncio
async def test_save_recordings_setting_roundtrip(client: AsyncClient) -> None:
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"save_recordings": False},
    )
    assert saved.status_code == 200
    assert saved.json()["save_recordings"] is False
    loaded = await client.get("/setup/settings", headers=auth())
    assert loaded.json()["save_recordings"] is False


@pytest.mark.asyncio
async def test_save_recordings_does_not_unload_asr(client: AsyncClient, app) -> None:
    asr = app.state.container.setup._asr
    asr.unload_calls = 0
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"save_recordings": False, "whisper_model": "small"},
    )
    assert saved.status_code == 200
    assert asr.unload_calls == 0


@pytest.mark.asyncio
async def test_new_whisper_model_unloads_asr(client: AsyncClient, app) -> None:
    asr = app.state.container.setup._asr
    asr.unload_calls = 0
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"whisper_model": "medium"},
    )
    assert saved.status_code == 200
    assert asr.unload_calls == 1


@pytest.mark.asyncio
async def test_recordings_dir_file_returns_400(client: AsyncClient, tmp_path) -> None:
    target = tmp_path / "not-a-folder.txt"
    target.write_text("x", encoding="utf-8")
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"recordings_dir": str(target)},
    )
    assert saved.status_code == 400
    assert "pasta" in saved.json()["detail"].lower()
