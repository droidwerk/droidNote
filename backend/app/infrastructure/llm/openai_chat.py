from __future__ import annotations

from collections.abc import Callable

import httpx

from app.application.prompts import SYSTEM_PROMPT
from app.core.logging import get_logger
from app.core.net_tls import ssl_verify
from app.domain.models import SetupComponentStatus

log = get_logger("llm.openai")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
CLOUD_LLM_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-4o-mini", "GPT-4o mini — recomendado, rápido e barato"),
    ("gpt-4o", "GPT-4o — melhor qualidade de nota"),
    ("gpt-4.1-mini", "GPT-4.1 mini — equilíbrio"),
)


class OpenAIChatEngine:
    """Gera as mesmas notas do motor local, usando a API OpenAI."""

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    def set_model(self, model: str) -> None:
        self.model = model

    def is_ready(self) -> bool:
        return bool(self.api_key.strip())

    async def status_component(self) -> SetupComponentStatus:
        if self.is_ready():
            return SetupComponentStatus(
                status="ready",
                progress=100,
                message=f"API OpenAI pronta ({self.model})",
            )
        return SetupComponentStatus(
            status="missing",
            progress=0,
            message="Informe a chave da API OpenAI nas preferências",
        )

    async def ensure_ready(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        if not self.is_ready():
            raise RuntimeError("Informe a chave da API OpenAI nas preferências.")
        if on_progress:
            on_progress(100, "API OpenAI pronta — sem download local")

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        return await self._complete(prompt, system=system or SYSTEM_PROMPT, json_mode=True)

    async def generate_json_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str:
        text = await self.generate_json(prompt, system=system)
        if text:
            on_token(text)
        return text

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        return await self._complete(prompt, system=system or SYSTEM_PROMPT, json_mode=False)

    async def generate_text_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str:
        text = await self.generate_text(prompt, system=system)
        if text:
            on_token(text)
        return text

    async def _complete(self, prompt: str, *, system: str, json_mode: bool) -> str:
        if not self.is_ready():
            raise RuntimeError("Informe a chave da API OpenAI nas preferências.")
        body: dict[str, object] = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=180.0, verify=ssl_verify()) as client:
            response = await client.post(
                OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                json=body,
            )
        if response.status_code >= 400:
            detail = _error_detail(response)
            log.warning("openai chat failed status=%s", response.status_code)
            raise RuntimeError(detail)
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message
    except ValueError:
        pass
    return f"OpenAI recusou a geração (HTTP {response.status_code})."
