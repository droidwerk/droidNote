from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import auth


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
