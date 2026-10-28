from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
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
from app.application.brief import BriefService
from app.application.documents import DocumentService
from app.application.meetings import MeetingWatcher, normalize_mode
from app.application.retention import RetentionService
from app.application.tasks import TaskService
from app.application.templates import TemplateService
from app.application.sessions import SessionService
from app.application.setup import SetupService
from app.application.speakers import SpeakersService
from app.application.summarize import SummarizeService
from app.application.voices import VoiceService
from app.core.config import Settings, get_settings, session_recording_path
from app.core.hardware import available_ram_gb, suggest_note_model, suggest_whisper_model, total_ram_gb
from app.core.i18n import normalize_ui_language, read_install_language
from app.core.logging import configure_logging, get_logger
from app.core.net_tls import install_system_trust
from app.infrastructure.asr.openai_engine import OpenAIWhisperEngine
from app.infrastructure.asr.router import AsrRouter
from app.infrastructure.asr.whisper_engine import WhisperEngine
from app.infrastructure.audio.factory import build_audio_capture
from app.infrastructure.llm.ollama_manager import OllamaManager
from app.infrastructure.llm.openai_chat import OpenAIChatEngine
from app.infrastructure.llm.router import LlmRouter
from app.infrastructure.persistence.sqlite import SqliteStore
from app.infrastructure.voice.embedder import OnnxVoiceEmbedder
from app.infrastructure.system.mic_usage import WindowsMicUsage

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


async def stop_abandoned_recordings(store: SqliteStore) -> None:
    """Sessão que ficou 'recording' porque o processo caiu não tem captura viva."""
    now = datetime.now(tz=UTC)
    for session in await store.list_sessions():
        if session.status != "recording":
            continue
        await store.update_session(
            replace(session, status="stopped", ended_at=session.ended_at or now)
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved = settings or get_settings()
    # Antes de qualquer download: em PC com proxy ou antivírus que inspeciona
    # HTTPS, a CA está só no Windows e o certifi sozinho recusa a conexão.
    install_system_trust(resolved.data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = SqliteStore(resolved.db_path)
        await store.initialize()
        await stop_abandoned_recordings(store)
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
        embedder = OnnxVoiceEmbedder(resolved.models_dir)
        voices = VoiceService(
            embedder,
            store,
            bus,
            recordings_path=lambda session_id: session_recording_path(resolved, session_id),
        )
        capture = CaptureService(resolved, audio, asr, store, bus, voices=voices, neural_vad=True)
        import asyncio

        capture.bind_loop(asyncio.get_running_loop())
        tasks = TaskService(store)
        container = AppContainer(
            settings=resolved,
            store=store,
            bus=bus,
            capture=capture,
            sessions=SessionService(store),
            summarize=SummarizeService(llm, store, tasks),
            setup=SetupService(resolved, store, audio, asr, llm, voice=embedder),
            llm=llm,
            speakers=SpeakersService(llm, store),
            chat=ChatService(llm, store),
            voices=voices,
        )
        app.state.container = container
        container.templates = TemplateService(store)
        await container.templates.ensure_builtins()
        container.tasks = tasks
        await tasks.backfill()
        container.brief = BriefService(store)
        container.documents = DocumentService(store, resolved.data_dir / "tmp")
        retention = RetentionService(store, lambda session_id: session_recording_path(resolved, session_id))
        container.retention = retention

        async def _retention_loop() -> None:
            # Primeira passada logo depois de abrir; depois a cada 6 horas.
            await asyncio.sleep(30)
            while True:
                try:
                    await retention.run()
                except Exception:
                    log.exception("retention failed")
                await asyncio.sleep(6 * 3600)

        retention_task = asyncio.create_task(_retention_loop())

        async def _meeting_mode() -> str:
            return normalize_mode(await store.get_setting("meeting_detection"))

        async def _auto_start(app_name: str) -> str | None:
            if capture.is_recording() or not asr.is_ready():
                return None
            from datetime import datetime as _dt

            mic_only = (await store.get_setting("mic_only_default")) == "1"
            state = await capture.start(
                mic_only=mic_only,
                title=f"{app_name} · {_dt.now():%d/%m/%Y %H:%M}",
                capture_mode="meeting",
            )
            return state.session_id

        async def _auto_stop() -> None:
            from app.api.v1.endpoints.capture import finish_session

            session_id = capture.state.session_id
            await capture.stop()
            if session_id:
                asyncio.create_task(finish_session(container, session_id))

        meetings = MeetingWatcher(
            WindowsMicUsage(),
            bus,
            get_mode=_meeting_mode,
            is_recording=capture.is_recording,
            current_session=lambda: capture.state.session_id,
            start_capture=_auto_start,
            stop_capture=_auto_stop,
        )
        container.meetings = meetings
        meetings.start()
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

        # Motor de voz: 26 MB, baixa sozinho na primeira execução e carrega
        # antes da primeira gravação.
        async def _prepare_voice() -> None:
            try:
                if not embedder.is_ready():
                    await container.setup.download_voice()
                if embedder.is_ready():
                    await asyncio.to_thread(embedder.load)
            except Exception:
                log.exception("voice engine prepare failed")

        voice_task = asyncio.create_task(_prepare_voice())

        yield
        if preload_task and not preload_task.done():
            preload_task.cancel()
        if not voice_task.done():
            voice_task.cancel()
        retention_task.cancel()
        await meetings.close()
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


class _ReadyServer(uvicorn.Server):
    """Só anuncia DROIDNOTE_READY quando a porta já aceita conexões.

    Antes o anúncio saía antes do uvicorn subir: o app instalado pegava a porta,
    perguntava o status na hora e levava "connection refused" ("Failed to fetch"
    na tela) enquanto o banco, os templates e os serviços ainda inicializavam.
    """

    def __init__(self, config: uvicorn.Config, payload: dict[str, object], runtime_path: Path) -> None:
        super().__init__(config)
        self._payload = payload
        self._runtime_path = runtime_path

    async def startup(self, sockets=None) -> None:  # type: ignore[override]
        await super().startup(sockets=sockets)
        if self.should_exit:
            return
        self._runtime_path.write_text(json.dumps(self._payload), encoding="utf-8")
        print(f"DROIDNOTE_READY {json.dumps(self._payload)}", flush=True)


def run() -> None:
    settings = get_settings()
    port = _bind_port(settings.host, settings.port)
    payload = {"host": settings.host, "port": port, "token": settings.token}
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    _ReadyServer(config, payload, settings.runtime_path).run()


if __name__ == "__main__":
    run()
