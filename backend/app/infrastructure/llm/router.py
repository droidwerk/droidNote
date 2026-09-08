from __future__ import annotations

from collections.abc import Callable

from app.domain.models import SetupComponentStatus
from app.infrastructure.llm.ollama_manager import OllamaManager
from app.infrastructure.llm.openai_chat import OpenAIChatEngine


class LlmRouter:
    """Encaminha as notas para o mesmo provedor escolhido para a transcrição."""

    def __init__(
        self,
        local: OllamaManager,
        openai: OpenAIChatEngine,
        provider: str = "neste_pc",
    ) -> None:
        self.local = local
        self.openai = openai
        self.provider = normalize_provider(provider)

    def set_provider(self, provider: str) -> None:
        self.provider = normalize_provider(provider)

    @property
    def is_cloud(self) -> bool:
        return self.provider == "openai"

    def _engine(self) -> OllamaManager | OpenAIChatEngine:
        return self.openai if self.is_cloud else self.local

    @property
    def model(self) -> str:
        return self._engine().model

    def set_model(self, model: str) -> None:
        self.local.set_model(model)

    def set_cloud_model(self, model: str) -> None:
        self.openai.set_model(model)

    def set_api_key(self, key: str) -> None:
        self.openai.api_key = key

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        return await self._engine().generate_json(prompt, system=system)

    async def generate_json_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str:
        return await self._engine().generate_json_stream(prompt, on_token, system=system)

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        return await self._engine().generate_text(prompt, system=system)

    async def generate_text_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str:
        return await self._engine().generate_text_stream(prompt, on_token, system=system)

    async def status_component(self) -> SetupComponentStatus:
        return await self._engine().status_component()

    async def ensure_ready(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        await self._engine().ensure_ready(on_progress)

    async def is_server_up(self) -> bool:
        if self.is_cloud:
            return self.openai.is_ready()
        return await self.local.is_server_up()


def normalize_provider(value: str) -> str:
    cleaned = (value or "neste_pc").strip().lower()
    if cleaned in {"openai", "api", "cloud"}:
        return "openai"
    return "neste_pc"
