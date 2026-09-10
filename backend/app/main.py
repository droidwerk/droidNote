from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.deps import AppContainer
from app.api.v1.router import api_router
from app.application.bus import EventBus
from app.application.capture import CaptureService
from app.application.chat import ChatService
from app.application.sessions import SessionService
from app.application.setup import SetupService
from app.application.speakers import SpeakersService
from app.application.summarize import SummarizeService
from app.core.config import Settings, get_settings
from app.core.hardware import available_ram_gb, suggest_note_model, suggest_whisper_model, total_ram_gb
from app.core.i18n import normalize_ui_language, read_install_language
from app.core.logging import configure_logging, get_logger
from app.infrastructure.asr.openai_engine import OpenAIWhisperEngine
from app.infrastructure.asr.router import AsrRouter
from app.infrastructure.asr.whisper_engine import WhisperEngine
from app.infrastructure.audio.factory import build_audio_capture
from app.infrastructure.llm.ollama_manager import OllamaManager
from app.infrastructure.llm.openai_chat import OpenAIChatEngine
from app.infrastructure.llm.router import LlmRouter
from app.infrastructure.persistence.sqlite import SqliteStore

log = get_logger("main")

ALLOWED_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://tauri.localhost",
    "http://tauri.localhost",
    "tauri://localhost",
]


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = SqliteStore(resolved.db_path)
        await store.initialize()
        saved_whisper = await store.get_setting("whisper_model")
        saved_ollama = await store.get_setting("ollama_model")
        saved_device = await store.get_setting("whisper_device")
        saved_provider = await store.get_setting("provider") or await store.get_setting("asr_provider")
        saved_cloud = await store.get_setting("asr_cloud_model")
        saved_llm_cloud = await store.get_setting("llm_cloud_model")
        saved_language = await store.get_setting("language")
        saved_ui_language = await store.get_setting("ui_language")
        saved_key = await store.get_setting("asr_api_key")
        saved_recordings = await store.get_setting("recordings_dir")
        if saved_whisper:
            resolved.whisper_model = saved_whisper
        if saved_ollama:
            resolved.ollama_model = saved_ollama
        else:
            # Primeira execução: escolhe o que a máquina aguenta em vez de assumir
            # um modelo grande e travar o PC do usuário.
            ram = available_ram_gb() or total_ram_gb()
            resolved.ollama_model = suggest_note_model(ram)
            resolved.whisper_model = saved_whisper or suggest_whisper_model(ram)
            log.info(
                "first run ram=%.1fGB note=%s whisper=%s",
                ram,
                resolved.ollama_model,
                resolved.whisper_model,
            )
            await store.set_setting("ollama_model", resolved.ollama_model)
            await store.set_setting("whisper_model", resolved.whisper_model)
        if saved_device:
            resolved.whisper_device = saved_device
        if saved_provider:
            resolved.provider = saved_provider
        if saved_cloud:
            resolved.asr_cloud_model = saved_cloud
        if saved_llm_cloud:
            resolved.llm_cloud_model = saved_llm_cloud
        if saved_language:
            resolved.language = saved_language
        if saved_ui_language:
            resolved.ui_language = saved_ui_language
        else:
            seeded = read_install_language(resolved.data_dir)
            if seeded:
                resolved.ui_language = normalize_ui_language(seeded)
        if saved_recordings:
            resolved.recordings_dir = Path(saved_recordings)
        audio = build_audio_capture(resolved.sample_rate)
        local = WhisperEngine(
            resolved.whisper_model,
            resolved.models_dir,
            device_policy=resolved.whisper_device,
        )
        openai = OpenAIWhisperEngine(api_key=saved_key or "", model=resolved.asr_cloud_model)
        asr = AsrRouter(local, openai, provider=resolved.provider)
        llm = LlmRouter(
            OllamaManager(resolved.ollama_base_url, resolved.ollama_model),
            OpenAIChatEngine(api_key=saved_key or "", model=resolved.llm_cloud_model),
            provider=resolved.provider,
        )
        bus = EventBus()
        capture = CaptureService(resolved, audio, asr, store, bus)
        import asyncio

        capture.bind_loop(asyncio.get_running_loop())
        container = AppContainer(
            settings=resolved,
            store=store,
            bus=bus,
            capture=capture,
            sessions=SessionService(store),
            summarize=SummarizeService(llm, store),
            setup=SetupService(resolved, store, audio, asr, llm),
            llm=llm,
            speakers=SpeakersService(llm, store),
            chat=ChatService(llm, store),
        )
        app.state.container = container
        log.info("backend ready")

        # Pré-carrega o Whisper local em segundo plano: quando o usuário
        # apertar gravar, o modelo já está na RAM e a transcrição começa
        # imediatamente, em vez de esperar o load completo.
        preload_task: asyncio.Task[None] | None = None
        if asr.provider != "openai" and local.is_ready():

            async def _preload_whisper() -> None:
                try:
                    await asyncio.to_thread(local.load)
                except Exception:
                    log.exception("whisper preload failed")

            preload_task = asyncio.create_task(_preload_whisper())

        yield
        if preload_task and not preload_task.done():
            preload_task.cancel()
        if capture.is_recording():
            await capture.stop()

    app = FastAPI(
        title="DroidNote",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()


def _bind_port(host: str, preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, preferred))
        return int(sock.getsockname()[1])


def run() -> None:
    settings = get_settings()
    port = _bind_port(settings.host, settings.port)
    payload = {"host": settings.host, "port": port, "token": settings.token}
    settings.runtime_path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"DROIDNOTE_READY {json.dumps(payload)}", flush=True)
    uvicorn.run(
        app,
        host=settings.host,
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    run()
