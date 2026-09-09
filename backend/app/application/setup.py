from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings, parse_recordings_dir
from app.core.logging import get_logger
from app.core.hardware import (
    DISK_MARGIN,
    OLLAMA_DOWNLOAD_GB,
    OLLAMA_INSTALLER_GB,
    WHISPER_DOWNLOAD_GB,
    available_ram_gb,
    disk_has_room,
    estimate_download_gb,
    suggest_note_model,
    suggest_whisper_model,
    total_ram_gb,
    vram_gb,
)
from app.core.user_errors import explain
from app.domain.models import SetupComponentStatus, SetupStatus
from app.domain.ports import AsrPort, AudioCapturePort, SessionRepository
from app.infrastructure.asr.openai_engine import CLOUD_ASR_MODELS
from app.infrastructure.asr.whisper_engine import catalog_whisper_models
from app.infrastructure.llm.ollama_manager import OLLAMA_CATALOG
from app.infrastructure.llm.openai_chat import CLOUD_LLM_MODELS
from app.infrastructure.llm.router import LlmRouter, normalize_provider
from app.schemas.api import BootstrapIn, SettingsIn, SettingsOut

log = get_logger("setup")


class SetupService:
    def __init__(
        self,
        settings: Settings,
        store: SessionRepository,
        audio: AudioCapturePort,
        asr: AsrPort,
        llm: LlmRouter,
    ) -> None:
        self._settings = settings
        self._store = store
        self._audio = audio
        self._asr = asr
        self._llm = llm
        self._whisper_status = self._whisper_component()
        self._task: asyncio.Task[None] | None = None
        self._preload_task: asyncio.Task[None] | None = None

    def _whisper_component(self) -> SetupComponentStatus:
        if self._asr.is_ready():
            return SetupComponentStatus(
                status="ready", progress=100, message="Modelo de transcrição pronto"
            )
        provider = getattr(self._asr, "provider", None) or self._settings.provider
        if provider == "openai":
            return SetupComponentStatus(
                status="missing",
                progress=0,
                message="Falta a chave da API OpenAI.",
            )
        return SetupComponentStatus(
            status="missing",
            progress=0,
            message="Modelo de transcrição ainda não baixado neste PC. O DroidNote vai baixar o Whisper agora.",
        )

    def _refresh_whisper_status(self) -> None:
        if self._whisper_status.status == "downloading":
            return
        current = self._whisper_component()
        if current.status == "ready" or self._whisper_status.status != "error":
            self._whisper_status = current

    async def status(self) -> SetupStatus:
        llm = await self._llm.status_component()
        self._refresh_whisper_status()
        disclaimer = (await self._store.get_setting("disclaimer_accepted")) == "1"
        probe = self._audio.probe()
        audio_ok = bool(probe.get("microphone"))
        audio_message = str(probe.get("message") or "")
        ram = available_ram_gb() or total_ram_gb()
        save_recordings = await self._save_recordings_flag()
        kind = (await self._store.get_setting("disclaimer_kind")) or "local"
        capture_ready = self._asr.is_ready()
        summarize_ready = llm.status == "ready"
        if capture_ready and summarize_ready:
            await self._store.set_setting("setup_complete", "1")
        setup_complete = (await self._store.get_setting("setup_complete")) == "1"
        return SetupStatus(
            llm=llm,
            whisper=self._whisper_status,
            disclaimer_accepted=disclaimer,
            audio_ok=audio_ok,
            capture_ready=capture_ready,
            summarize_ready=summarize_ready,
            audio_message=audio_message,
            provider=self._settings.provider,
            ram_gb=ram,
            suggested_note_model=suggest_note_model(ram),
            suggested_whisper_model=suggest_whisper_model(ram),
            ollama_binary=bool(self._llm.local.find_binary()),
            save_recordings=save_recordings,
            disclaimer_kind=kind,
            setup_complete=setup_complete,
        )

    async def plan(self) -> dict[str, object]:
        ram = available_ram_gb() or total_ram_gb()
        catalog = await self.list_models()
        save_recordings = await self._save_recordings_flag()
        need_installer = not bool(self._llm.local.find_binary())
        whisper_installed = any(
            row.get("id") == self._settings.whisper_model and row.get("installed")
            for row in catalog["whisper"]
        )
        note_installed = any(
            row.get("id") == self._llm.local.model and row.get("installed")
            for row in catalog["ollama"]
        )
        download = estimate_download_gb(
            whisper_id=self._settings.whisper_model,
            note_id=self._llm.local.model,
            need_installer=need_installer,
            whisper_installed=bool(whisper_installed),
            note_installed=bool(note_installed),
        )
        disk_ok, free, needed = disk_has_room(self._settings.data_dir, download)
        return {
            "ram_gb": ram,
            "vram_gb": vram_gb(),
            "suggested_note_model": suggest_note_model(ram),
            "suggested_whisper_model": suggest_whisper_model(ram),
            "ollama_binary": bool(self._llm.local.find_binary()),
            "ollama_online": catalog["ollama_online"],
            "current_note_model": self._llm.local.model,
            "current_whisper_model": self._settings.whisper_model,
            "provider": self._settings.provider,
            "whisper": catalog["whisper"],
            "ollama": catalog["ollama"],
            "asr_cloud": catalog["asr_cloud"],
            "llm_cloud": catalog["llm_cloud"],
            "save_recordings": save_recordings,
            "free_disk_gb": free,
            "download_gb": download,
            "required_disk_gb": needed,
            "disk_ok": disk_ok,
            "disk_margin": DISK_MARGIN,
            "whisper_download_gb": WHISPER_DOWNLOAD_GB,
            "ollama_download_gb": OLLAMA_DOWNLOAD_GB,
            "ollama_installer_gb": OLLAMA_INSTALLER_GB,
        }

    async def accept_disclaimer(self, kind: str = "local") -> None:
        cleaned = "openai" if kind == "openai" else "local"
        await self._store.set_setting("disclaimer_accepted", "1")
        await self._store.set_setting("disclaimer_kind", cleaned)
        if cleaned == "openai":
            await self._store.set_setting("openai_disclaimer_accepted", "1")

    async def start_bootstrap(self, payload: BootstrapIn | None = None) -> None:
        if payload is not None:
            await self.apply_settings(
                SettingsIn(
                    provider=payload.provider,
                    ollama_model=payload.ollama_model,
                    whisper_model=payload.whisper_model,
                    save_recordings=payload.save_recordings,
                )
            )
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._bootstrap())

    async def _bootstrap(self) -> None:
        def whisper_progress(progress: int, message: str) -> None:
            self._whisper_status = SetupComponentStatus(
                status="downloading" if progress < 100 else "ready",
                progress=progress,
                message=message,
            )

        if self._settings.provider == "openai":
            if self._asr.is_ready():
                whisper_progress(100, "Transcrição pela API OpenAI — sem download local")
            else:
                self._whisper_status = SetupComponentStatus(
                    status="error",
                    progress=0,
                    message=explain(
                        "Falta a chave da API OpenAI.",
                        severe=True,
                        app_will="O DroidNote não vai transcrever na nuvem sem ela.",
                        user_can="Cole a chave em Preferências ou volte e escolha “neste computador”.",
                    ),
                )
            try:
                await self._llm.ensure_ready()
            except Exception:
                return
            return

        if not await self._guard_disk():
            return

        try:
            if not self._asr.is_ready():
                whisper_progress(1, "Baixando modelo de transcrição")
                await asyncio.to_thread(self._asr.download, whisper_progress)
            else:
                whisper_progress(100, "Modelo de transcrição pronto")
        except Exception as exc:
            self._whisper_status = SetupComponentStatus(
                status="error",
                progress=0,
                message=_friendly_download_error(exc, kind="whisper"),
            )

        try:
            await self._llm.ensure_ready()
        except Exception as exc:
            if self._llm.local.component.status != "error":
                self._llm.local.component = SetupComponentStatus(
                    status="error",
                    progress=0,
                    message=_friendly_download_error(exc, kind="ollama"),
                )
            return

    async def _guard_disk(self) -> bool:
        note_installed = False
        if await self._llm.local.is_server_up():
            note_installed = await self._llm.local.has_model()
        download = estimate_download_gb(
            whisper_id=self._settings.whisper_model,
            note_id=self._settings.ollama_model,
            need_installer=self._llm.local.find_binary() is None,
            whisper_installed=self._asr.is_ready(),
            note_installed=note_installed,
        )
        ok, free, needed = disk_has_room(self._settings.data_dir, download)
        if ok:
            return True
        missing = max(0.0, needed - free)
        message = explain(
            f"Neste disco há {free:.1f} GB livres, e o download precisa de cerca de {needed:.1f} GB.",
            severe=True,
            app_will="O DroidNote não começou o download para não encher o disco.",
            user_can=f"Liberar pelo menos {missing:.1f} GB e tocar em Tentar de novo.",
        )
        self._whisper_status = SetupComponentStatus(status="error", progress=0, message=message)
        self._llm.local.component = SetupComponentStatus(status="error", progress=0, message=message)
        return False

    def _preload_asr(self) -> None:
        """Baixa ou recarrega o Whisper local em segundo plano para a próxima gravação começar na hora."""
        asr = self._asr
        if getattr(asr, "provider", self._settings.provider) == "openai":
            return
        local = getattr(asr, "local", asr)

        async def _ensure() -> None:
            def whisper_progress(progress: int, message: str) -> None:
                self._whisper_status = SetupComponentStatus(
                    status="downloading" if progress < 100 else "ready",
                    progress=progress,
                    message=message,
                )

            try:
                if hasattr(local, "download") and not local.is_ready():
                    whisper_progress(1, "Baixando modelo de transcrição")
                    await asyncio.to_thread(local.download, whisper_progress)
                if hasattr(local, "load") and local.is_ready():
                    await asyncio.to_thread(local.load)
            except Exception as exc:
                log.exception("whisper preload failed")
                self._whisper_status = SetupComponentStatus(
                    status="error",
                    progress=0,
                    message=_friendly_download_error(exc, kind="whisper"),
                )

        if self._preload_task and not self._preload_task.done():
            self._preload_task.cancel()
        self._preload_task = asyncio.create_task(_ensure())

    async def apply_settings(self, payload: SettingsIn) -> None:
        asr = self._asr
        asr_changed = False
        if payload.whisper_model:
            model = payload.whisper_model
            changed = model != self._settings.whisper_model
            self._settings.whisper_model = model
            if hasattr(asr, "model_size"):
                asr.model_size = model
            if changed and hasattr(asr, "unload"):
                asr.unload()
                asr_changed = True
            await self._store.set_setting("whisper_model", model)
        if payload.ollama_model:
            self._llm.set_model(payload.ollama_model)
            self._settings.ollama_model = payload.ollama_model
            await self._store.set_setting("ollama_model", payload.ollama_model)
        if payload.mic_only_default is not None:
            await self._store.set_setting(
                "mic_only_default", "1" if payload.mic_only_default else "0"
            )
        if payload.whisper_device:
            policy = payload.whisper_device.lower().strip()
            if policy in {"auto", "cpu", "cuda"}:
                changed = policy != self._settings.whisper_device
                self._settings.whisper_device = policy
                if hasattr(asr, "device_policy"):
                    asr.device_policy = policy
                if changed and policy == "cuda" and hasattr(asr, "clear_cpu_cache"):
                    asr.clear_cpu_cache()
                if changed and hasattr(asr, "unload"):
                    asr.unload()
                    asr_changed = True
                await self._store.set_setting("whisper_device", policy)
        if payload.language is not None:
            language = payload.language.strip().lower() or "pt"
            if language in {"pt", "en", "es", "auto"}:
                self._settings.language = language
                await self._store.set_setting("language", language)
        if payload.asr_cloud_model:
            model = payload.asr_cloud_model.strip()
            self._settings.asr_cloud_model = model
            openai = getattr(asr, "openai", None)
            if openai is not None:
                openai.model = model
            await self._store.set_setting("asr_cloud_model", model)
        if payload.llm_cloud_model:
            model = payload.llm_cloud_model.strip()
            self._settings.llm_cloud_model = model
            self._llm.set_cloud_model(model)
            await self._store.set_setting("llm_cloud_model", model)
        if payload.asr_api_key is not None:
            key = payload.asr_api_key.strip()
            if not _is_masked_key(key):
                setter = getattr(asr, "set_api_key", None)
                if callable(setter):
                    setter(key)
                else:
                    openai = getattr(asr, "openai", None)
                    if openai is not None:
                        openai.api_key = key
                self._llm.set_api_key(key)
                await self._store.set_setting("asr_api_key", key)
        if payload.provider:
            provider = normalize_provider(payload.provider)
            if provider != self._settings.provider:
                asr_changed = True
            self._settings.provider = provider
            setter = getattr(asr, "set_provider", None)
            if callable(setter):
                setter(provider)
            elif hasattr(asr, "provider"):
                asr.provider = provider
            self._llm.set_provider(provider)
            await self._store.set_setting("provider", provider)
        if payload.self_person_id is not None:
            await self._store.set_setting("self_person_id", payload.self_person_id.strip())
        if payload.recordings_dir is not None:
            folder = parse_recordings_dir(payload.recordings_dir, self._settings.data_dir)
            self._settings.recordings_dir = folder
            await self._store.set_setting("recordings_dir", str(folder))
        if payload.save_recordings is not None:
            await self._store.set_setting(
                "save_recordings", "1" if payload.save_recordings else "0"
            )
        if payload.openai_disclaimer_accepted:
            await self._store.set_setting("openai_disclaimer_accepted", "1")
        if asr_changed:
            self._preload_asr()

    async def settings_out(self) -> SettingsOut:
        mic_only = (await self._store.get_setting("mic_only_default")) == "1"
        stored_key = await self._store.get_setting("asr_api_key")
        key = stored_key or ""
        openai = getattr(self._asr, "openai", None)
        if openai is not None and getattr(openai, "api_key", ""):
            key = openai.api_key
        self_person = await self._store.get_setting("self_person_id")
        openai_ok = (await self._store.get_setting("openai_disclaimer_accepted")) == "1"
        kind = (await self._store.get_setting("disclaimer_kind")) or "local"
        return SettingsOut(
            whisper_model=self._settings.whisper_model,
            ollama_model=self._llm.local.model,
            mic_only_default=mic_only,
            whisper_device=self._settings.whisper_device,
            provider=self._settings.provider,
            asr_cloud_model=self._settings.asr_cloud_model,
            llm_cloud_model=self._settings.llm_cloud_model,
            has_api_key=bool(key.strip()),
            api_key_hint=key.strip()[-4:] if len(key.strip()) >= 4 else "",
            language=self._settings.language or "pt",
            data_dir=str(self._settings.data_dir),
            recordings_dir=str(self._settings.resolve_recordings_dir()),
            self_person_id=self_person or "",
            save_recordings=await self._save_recordings_flag(),
            openai_disclaimer_accepted=openai_ok,
            disclaimer_kind=kind,
        )

    async def test_api_key(self, key: str | None) -> tuple[bool, str]:
        tester = getattr(self._asr, "test_api_key", None)
        if callable(tester):
            return tester(key)
        openai = getattr(self._asr, "openai", None)
        if openai is not None and hasattr(openai, "test_key"):
            return openai.test_key(key)
        stored = (key if key is not None else await self._store.get_setting("asr_api_key")) or ""
        if not stored.strip():
            return False, "Informe uma chave da API OpenAI."
        return False, "Motor OpenAI indisponível neste modo."

    async def list_models(self) -> dict[str, object]:
        whisper = catalog_whisper_models(self._settings.models_dir, self._settings.whisper_model)
        for row in whisper:
            row["learn_more"] = _whisper_learn_more(str(row["id"]))
        ollama_online = await self._llm.local.is_server_up()
        installed: set[str] = set()
        ollama_rows: list[dict[str, str | bool]] = []
        if ollama_online:
            for item in await self._llm.local.list_models():
                installed.add(item["id"])
                ollama_rows.append(
                    {
                        "id": item["id"],
                        "label": item["label"],
                        "installed": True,
                        "source": "ollama",
                        "detail": item.get("detail") or "",
                        "recommended": _is_recommended(item["id"]),
                        "learn_more": _ollama_learn_more(item["id"]),
                    }
                )
        for model_id, label in OLLAMA_CATALOG:
            if any(row["id"] == model_id for row in ollama_rows):
                continue
            ollama_rows.append(
                {
                    "id": model_id,
                    "label": label,
                    "installed": False,
                    "source": "ollama",
                    "detail": "",
                    "recommended": _is_recommended(model_id),
                    "learn_more": _ollama_learn_more(model_id),
                }
            )
        current = self._llm.local.model
        if current and not any(row["id"] == current for row in ollama_rows):
            ollama_rows.insert(
                0,
                {
                    "id": current,
                    "label": current,
                    "installed": any(name.startswith(current) for name in installed),
                    "source": "ollama",
                    "detail": "" if ollama_online else "Servidor Ollama offline",
                    "recommended": _is_recommended(current),
                    "learn_more": _ollama_learn_more(current),
                },
            )
        return {
            "whisper": whisper,
            "ollama": ollama_rows,
            "asr_cloud": _cloud_rows(CLOUD_ASR_MODELS),
            "llm_cloud": _cloud_rows(CLOUD_LLM_MODELS),
            "ollama_online": ollama_online,
        }

    async def _save_recordings_flag(self) -> bool:
        stored = await self._store.get_setting("save_recordings")
        if stored is None:
            return True
        return stored != "0"

    def export_diagnostics(self) -> Path:
        from app.application.diagnostics import write_diagnostic_zip

        return write_diagnostic_zip(self._settings)


def _friendly_download_error(exc: BaseException, *, kind: str) -> str:
    text = str(exc).strip()
    if "adulterado" in text.lower() or "corrompido" in text.lower():
        return text if "impede" in text.lower() else explain(
            text,
            severe=True,
            app_will="O arquivo não foi executado.",
            user_can="Tente de novo. Se repetir, baixe o Ollama em ollama.com e volte ao DroidNote.",
        )
    if "espaço" in text.lower() or "disk" in text.lower() or "GB livres" in text:
        return text
    lowered = text.lower()
    network = any(token in lowered for token in ("timeout", "timed out", "connect", "network", "proxy", "403", "451"))
    if network:
        return explain(
            "A internet falhou no meio do download.",
            severe=True,
            app_will="O DroidNote parou e não trata o arquivo incompleto como pronto.",
            user_can="Verifique a rede, VPN ou firewall e toque em Tentar de novo.",
        )
    if kind == "whisper":
        return explain(
            "Não deu para baixar ou conferir o modelo de transcrição.",
            severe=True,
            app_will="A transcrição local fica pausada até isso funcionar.",
            user_can="Tente de novo. Se o antivírus bloqueou, permita o DroidNote e o download.",
        )
    return explain(
        text if text else "Não deu para preparar o motor de notas.",
        severe=True,
        app_will="O DroidNote não executou instalador nem modelo incompleto.",
        user_can="Tente de novo ou instale o Ollama em ollama.com e volte.",
    )


def _cloud_rows(catalog: tuple[tuple[str, str], ...]) -> list[dict[str, str | bool]]:
    return [
        {
            "id": model_id,
            "label": label,
            "installed": True,
            "source": "openai",
            "detail": "",
            "recommended": "recomendado" in label.lower(),
            "learn_more": "https://platform.openai.com/docs/models",
        }
        for model_id, label in catalog
    ]


def _is_recommended(model_id: str) -> bool:
    return any(model_id.startswith(item) for item, label in OLLAMA_CATALOG if "recomendado" in label.lower())


def _ollama_learn_more(model_id: str) -> str:
    name = model_id.split(":")[0].strip() or model_id
    return f"https://ollama.com/library/{name}"


def _whisper_learn_more(model_id: str) -> str:
    return f"https://huggingface.co/Systran/faster-whisper-{model_id}"


def _is_masked_key(value: str) -> bool:
    return bool(value) and set(value) <= {"•", "*"}
