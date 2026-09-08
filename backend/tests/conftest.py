from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.deps import AppContainer
from app.application.bus import EventBus
from app.application.capture import CaptureService
from app.application.sessions import SessionService
from app.application.setup import SetupService
from app.application.speakers import SpeakersService
from app.application.summarize import SummarizeService
from app.core.config import Settings, get_settings
from app.infrastructure.llm.ollama_manager import OllamaManager
from app.infrastructure.llm.openai_chat import OpenAIChatEngine
from app.infrastructure.llm.router import LlmRouter
from app.infrastructure.persistence.sqlite import SqliteStore
from app.main import create_app
from tests.fakes import FakeAsr, FakeAudioCapture, FakeLlm

TOKEN = "test-token-droidnote"


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("DROIDNOTE_TOKEN", TOKEN)
    get_settings.cache_clear()
    return Settings(
        host="127.0.0.1",
        port=0,
        token=TOKEN,
        data_dir=tmp_path,
        whisper_model="small",
        ollama_model="qwen2.5:3b",
    )


@pytest.fixture
async def app(settings: Settings):
    application = create_app(settings)
    store = SqliteStore(settings.db_path)
    await store.initialize()
    audio = FakeAudioCapture()
    asr = FakeAsr()
    router = LlmRouter(
        OllamaManager(settings.ollama_base_url, settings.ollama_model),
        OpenAIChatEngine(model=settings.llm_cloud_model),
        provider=settings.provider,
    )
    bus = EventBus()
    capture = CaptureService(settings, audio, asr, store, bus)
    capture.bind_loop(asyncio.get_running_loop())
    llm = FakeLlm()
    application.state.container = AppContainer(
        settings=settings,
        store=store,
        bus=bus,
        capture=capture,
        sessions=SessionService(store),
        summarize=SummarizeService(llm, store),
        setup=SetupService(settings, store, audio, asr, router),
        llm=router,
        speakers=SpeakersService(llm, store),
    )
    yield application
    if capture.is_recording():
        await capture.stop()
    await capture.wait_all_drains()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as ac:
        yield ac


def auth() -> dict[str, str]:
    return {"X-DroidNote-Token": TOKEN}
