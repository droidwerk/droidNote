from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import capture, chat, health, people, sessions, setup, tags, ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(capture.router)
api_router.include_router(sessions.router)
api_router.include_router(setup.router)
api_router.include_router(people.router)
api_router.include_router(tags.router)
api_router.include_router(chat.router)
api_router.include_router(ws.router)
