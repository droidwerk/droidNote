from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.conftest import auth


@pytest.mark.asyncio
async def test_status_marks_whisper_missing_when_local_not_ready(client: AsyncClient, app) -> None:
    app.state.container.setup._asr.ready = False
    response = await client.get("/setup/status", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert body["capture_ready"] is False
    assert body["whisper"]["status"] == "missing"
    assert "baixado" in body["whisper"]["message"].lower()


@pytest.mark.asyncio
async def test_switching_to_local_downloads_whisper(client: AsyncClient, app) -> None:
    asr = app.state.container.setup._asr
    asr.ready = False
    asr.downloaded = False
    to_cloud = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"provider": "openai", "asr_api_key": "sk-test-key"},
    )
    assert to_cloud.status_code == 200
    back = await client.put("/setup/settings", headers=auth(), json={"provider": "neste_pc"})
    assert back.status_code == 200
    task = app.state.container.setup._preload_task
    if task is not None:
        await asyncio.wait_for(task, timeout=2)
    assert asr.downloaded is True
    assert asr.ready is True


@pytest.mark.asyncio
async def test_list_local_models_catalog(client: AsyncClient) -> None:
    response = await client.get("/setup/models", headers=auth())
    assert response.status_code == 200
    body = response.json()
    whisper_ids = [item["id"] for item in body["whisper"]]
    assert "small" in whisper_ids
    assert "large-v3-turbo" in whisper_ids
    assert body["ollama_online"] in {True, False}
    assert isinstance(body["ollama"], list)
