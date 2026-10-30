from __future__ import annotations

from collections.abc import Callable

import httpx

from app.application.prompts import SYSTEM_PROMPT
from app.core.logging import get_logger
from app.core.net_tls import ssl_verify
from app.domain.models import SetupComponentStatus

log = get_logger("llm.openai")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
# Preço por milhão de tokens (entrada / saída): gpt-6-luna US$ 0,10 / 0,50;
# gpt-5.6-luna US$ 0,20 / 1,20; gpt-5.6-terra US$ 2 / 12.
# A interface traduz nome e explicação (models.* e modelHelp.*); aqui fica o nome curto de reserva.
DEFAULT_CLOUD_LLM_MODEL = "gpt-6-luna"
CLOUD_LLM_MODELS: tuple[tuple[str, str], ...] = (
    (DEFAULT_CLOUD_LLM_MODEL, "GPT-6 Luna — recomendado"),
    ("gpt-5.6-luna", "GPT-5.6 Luna"),
    ("gpt-5.6-terra", "GPT-5.6 Terra"),
)
# Modelos de chat que a OpenAI descontinuou (gpt-4o e gpt-4.1 desligam em 14/01/2027).
# Quem ainda tem um deles salvo passa para o equivalente atual sem precisar mexer em nada.
LEGACY_CLOUD_LLM_MODELS: dict[str, str] = {
    "gpt-4o-mini": DEFAULT_CLOUD_LLM_MODEL,
    "gpt-4.1-mini": DEFAULT_CLOUD_LLM_MODEL,
    "gpt-4.1-nano": DEFAULT_CLOUD_LLM_MODEL,
    "gpt-4o": "gpt-5.6-terra",
    "gpt-4.1": "gpt-5.6-terra",
}
# Modelos que aceitam `reasoning_effort: "none"`: respondem direto, como os gpt-4o faziam,
# e por isso ainda aceitam `temperature`. Os que sempre raciocinam recusam temperature.
_NO_REASONING_MODELS = frozenset(
    {"gpt-6-luna", "gpt-6-sol", "gpt-6.1-terra", "gpt-5.6-luna", "gpt-5.6-terra"}
)
_TUNING_PARAMS = ("temperature", "reasoning_effort", "response_format")


def normalize_cloud_llm_model(value: str | None) -> str:
    """Nome do modelo como fica salvo: vazio ou descontinuado vira o equivalente atual."""
    cleaned = (value or "").strip()
    if not cleaned:
        return DEFAULT_CLOUD_LLM_MODEL
    if cleaned in LEGACY_CLOUD_LLM_MODELS:
        return LEGACY_CLOUD_LLM_MODELS[cleaned]
    if cleaned.startswith("gpt-4"):
        return DEFAULT_CLOUD_LLM_MODEL
    return cleaned


def request_tuning(model: str) -> dict[str, object]:
    """Parâmetros de geração que cada família aceita no Chat Completions."""
    if model in _NO_REASONING_MODELS:
        return {"reasoning_effort": "none", "temperature": 0}
    if model.startswith(("gpt-5", "gpt-6")):
        # Raciocínio obrigatório: "low" segura custo e tempo da ata.
        return {"reasoning_effort": "low"}
    return {"temperature": 0}


class OpenAIChatEngine:
    """Gera as mesmas notas do motor local, usando a API OpenAI."""

    def __init__(self, api_key: str = "", model: str = DEFAULT_CLOUD_LLM_MODEL) -> None:
        self.api_key = api_key
        self.model = normalize_cloud_llm_model(model)

    def set_model(self, model: str) -> None:
        self.model = normalize_cloud_llm_model(model)

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

    def build_body(self, prompt: str, *, system: str, json_mode: bool) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            **request_tuning(self.model),
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def _complete(self, prompt: str, *, system: str, json_mode: bool) -> str:
        if not self.is_ready():
            raise RuntimeError("Informe a chave da API OpenAI nas preferências.")
        body = self.build_body(prompt, system=system, json_mode=json_mode)
        async with httpx.AsyncClient(timeout=180.0, verify=ssl_verify()) as client:
            for _attempt in range(len(_TUNING_PARAMS) + 1):
                response = await client.post(
                    OPENAI_CHAT_URL,
                    headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                    json=body,
                )
                if response.status_code != 400:
                    break
                # Um modelo novo pode recusar um parâmetro de ajuste ("Unsupported parameter:
                # 'temperature'..."); tira só esse e tenta de novo em vez de perder a ata.
                rejected = _rejected_param(_error_detail(response), body)
                if not rejected:
                    break
                log.warning("openai chat model=%s rejected param=%s; retrying without it", self.model, rejected)
                body.pop(rejected)
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


def _rejected_param(detail: str, body: dict[str, object]) -> str | None:
    lowered = detail.lower()
    for name in _TUNING_PARAMS:
        if name in body and name in lowered:
            return name
    return None


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
