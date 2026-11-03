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


@pytest.mark.asyncio
async def test_unhandled_error_is_json_with_cors(client: AsyncClient, app) -> None:
    """Uma falha inesperada no servidor chega ao app como 500 legível, com CORS,
    e não como "Failed to fetch"."""
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("No module named 'PIL'")

    app.include_router(router)
    response = await client.get("/boom", headers={**auth(), "Origin": "http://localhost:1420"})
    assert response.status_code == 500
    assert "PIL" in response.json()["detail"]
    assert response.headers.get("access-control-allow-origin") == "http://localhost:1420"
