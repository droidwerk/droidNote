from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import auth


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["capture"] == "idle"


@pytest.mark.asyncio
async def test_protected_route_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.get("/sessions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_rejects_wrong_token(client: AsyncClient) -> None:
    response = await client.get("/sessions", headers={"X-DroidNote-Token": "nope"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_accepts_token(client: AsyncClient) -> None:
    response = await client.get("/sessions", headers=auth())
    assert response.status_code == 200
    assert response.json() == []
