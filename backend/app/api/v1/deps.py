from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from app.application.bus import EventBus
from app.application.capture import CaptureService
from app.application.chat import ChatService
from app.application.sessions import SessionService
from app.application.setup import SetupService
from app.application.speakers import SpeakersService
from app.application.summarize import SummarizeService
from app.core.config import Settings
from app.infrastructure.llm.router import LlmRouter
from app.infrastructure.persistence.sqlite import SqliteStore


@dataclass
class AppContainer:
    settings: Settings
    store: SqliteStore
    bus: EventBus
    capture: CaptureService
    sessions: SessionService
    summarize: SummarizeService
    setup: SetupService
    llm: LlmRouter
    speakers: SpeakersService
    chat: ChatService


def get_container(app: FastAPI) -> AppContainer:
    return app.state.container
