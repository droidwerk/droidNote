from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.deps import AppContainer
from app.application.bus import EventBus
from app.application.capture import CaptureService
from app.application.chat import ChatService
from app.application.sessions import SessionService
from app.application.tasks import TaskService
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
    # TLS só com o certifi: o app não grava nem lê o trust-bundle.pem da pasta
    # real do DroidNote (um app aberto reescrevendo esse arquivo derrubava o teste).
    import certifi

    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.setenv(key, certifi.where())
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
        summarize=SummarizeService(llm, store, TaskService(store)),
        setup=SetupService(settings, store, audio, asr, router),
        llm=router,
        speakers=SpeakersService(llm, store),
        chat=ChatService(llm, store),
    )
    yield application
    if capture.is_recording():
        await capture.stop()
    await capture.wait_all_drains()
    # Tasks de fundo (worker de janelas, flush que o stop abandona) ainda podem
    # estar no meio de um acesso ao banco: esperar evita a thread do aiosqlite
    # tentar falar com um loop já fechado no próximo teste.
    pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=15)
        for task in pending:
            if not task.done():
                task.cancel()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as ac:
        yield ac


def auth() -> dict[str, str]:
    return {"X-DroidNote-Token": TOKEN}
