from __future__ import annotations

from collections.abc import Callable, Sequence

from app.infrastructure.asr.openai_engine import OpenAIWhisperEngine
from app.infrastructure.asr.whisper_engine import WhisperEngine


class AsrRouter:
    def __init__(
        self,
        local: WhisperEngine,
        openai: OpenAIWhisperEngine,
        provider: str = "neste_pc",
    ) -> None:
        self.local = local
        self.openai = openai
        self.provider = _normalize_provider(provider)

    def set_provider(self, provider: str) -> None:
        next_provider = _normalize_provider(provider)
        if next_provider == "openai":
            self.local.unload()
        self.provider = next_provider

    def _engine(self) -> WhisperEngine | OpenAIWhisperEngine:
        if self.provider == "openai":
            return self.openai
        return self.local

    def is_ready(self) -> bool:
        return self._engine().is_ready()

    def is_loaded(self) -> bool:
        return self._engine().is_loaded()

    @property
    def device(self) -> str:
        return self._engine().device

    @property
    def model_size(self) -> str:
        return self.local.model_size

    @model_size.setter
    def model_size(self, value: str) -> None:
        self.local.model_size = value

    @property
    def device_policy(self) -> str:
        return self.local.device_policy

    @device_policy.setter
    def device_policy(self, value: str) -> None:
        self.local.device_policy = value

    def clear_cpu_cache(self) -> None:
        self.local.clear_cpu_cache()

    def download(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        self._engine().download(on_progress)

    def load(self) -> None:
        self._engine().load()

    def unload(self) -> None:
        self.local.unload()
        self.openai.unload()

    def transcribe_window(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[str, str | None]:
        return self._engine().transcribe_window(
            samples,
            sample_rate,
            language=language,
        )

    def set_api_key(self, key: str) -> None:
        self.openai.api_key = key

    def test_api_key(self, key: str | None = None) -> tuple[bool, str]:
        return self.openai.test_key(key)


def _normalize_provider(value: str) -> str:
    cleaned = (value or "neste_pc").strip().lower()
    if cleaned in {"openai", "api", "cloud"}:
        return "openai"
    return "neste_pc"
