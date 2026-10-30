from __future__ import annotations

import io
import wave
from collections.abc import Callable, Sequence

import httpx
import numpy as np

from app.core.logging import get_logger
from app.core.net_tls import ssl_verify
from app.infrastructure.asr.whisper_engine import build_asr_prompt, filter_transcript, whisper_language_arg

log = get_logger("asr.openai")

OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
# Preço por minuto de áudio (tabela da OpenAI): gpt-transcribe US$ 0,0045.
# A interface traduz nome e explicação (models.* e modelHelp.*); aqui fica o nome curto de reserva.
DEFAULT_CLOUD_ASR_MODEL = "gpt-transcribe"
CLOUD_ASR_MODELS: tuple[tuple[str, str], ...] = (
    (DEFAULT_CLOUD_ASR_MODEL, "GPT Transcribe — recomendado"),
)
CLOUD_MODELS = CLOUD_ASR_MODELS
# Modelos que a OpenAI descontinuou (desligam em 26/02/2027). Quem ainda tem um deles salvo
# passa para o gpt-transcribe sem precisar mexer em nada. Os modelos de tempo real
# (gpt-live-transcribe, gpt-realtime-whisper) só existem em sessões Realtime por WebSocket;
# o DroidNote manda janelas de áudio pelo endpoint de arquivos, então não entram aqui.
LEGACY_CLOUD_ASR_MODELS: dict[str, str] = {
    "gpt-4o-transcribe": DEFAULT_CLOUD_ASR_MODEL,
    "gpt-4o-mini-transcribe": DEFAULT_CLOUD_ASR_MODEL,
    "gpt-4o-mini-transcribe-2025-12-15": DEFAULT_CLOUD_ASR_MODEL,
    "gpt-4o-transcribe-diarize": DEFAULT_CLOUD_ASR_MODEL,
    "whisper-1": DEFAULT_CLOUD_ASR_MODEL,
}


def normalize_cloud_asr_model(value: str | None) -> str:
    """Nome do modelo como fica salvo: vazio ou descontinuado vira o padrão atual."""
    cleaned = (value or "").strip()
    if not cleaned:
        return DEFAULT_CLOUD_ASR_MODEL
    if cleaned in LEGACY_CLOUD_ASR_MODELS:
        return LEGACY_CLOUD_ASR_MODELS[cleaned]
    if cleaned.startswith("gpt-4o-") and "transcribe" in cleaned:
        return DEFAULT_CLOUD_ASR_MODEL
    return cleaned


class OpenAIWhisperEngine:
    def __init__(self, api_key: str = "", model: str = DEFAULT_CLOUD_ASR_MODEL) -> None:
        self.api_key = api_key
        self.model = normalize_cloud_asr_model(model)
        self._device = "api"

    def is_ready(self) -> bool:
        return bool(self.api_key.strip())

    def is_loaded(self) -> bool:
        return self.is_ready()

    @property
    def device(self) -> str:
        return self._device

    def download(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        if on_progress:
            on_progress(100, "API OpenAI — sem download local")

    def load(self) -> None:
        if not self.is_ready():
            raise RuntimeError("Informe a chave da API OpenAI nas preferências.")

    def unload(self) -> None:
        return

    def transcribe_window(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[str, str | None]:
        self.load()
        locked = whisper_language_arg(language)
        wav = samples_to_wav_bytes(samples, sample_rate)
        data: dict[str, object] = {"model": self.model}
        prompt = build_asr_prompt(locked)
        if prompt:
            data["prompt"] = prompt
        if locked:
            data.update(_language_fields(self.model, locked))
        with httpx.Client(timeout=60.0, verify=ssl_verify()) as client:
            response = client.post(
                OPENAI_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                data=data,
                files={"file": ("audio.wav", wav, "audio/wav")},
            )
        if response.status_code >= 400:
            detail = _error_detail(response)
            log.warning("openai transcribe failed status=%s", response.status_code)
            raise RuntimeError(detail)
        payload = response.json()
        raw_text = str(payload.get("text") or "")
        if not raw_text and isinstance(payload.get("segments"), list):
            raw_text = " ".join(
                str(item.get("text") or "").strip() for item in payload["segments"] if isinstance(item, dict)
            )
        text = filter_transcript(raw_text, locked)
        return text, locked or _detected_language(payload)

    def transcribe_words(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[list[tuple[float, float, str]], str | None]:
        """Trechos com tempo. O gpt-transcribe devolve o texto da janela inteira sem
        marcação de tempo nem de falante, então a janela volta como um trecho só;
        quem falou em cada pedaço continua vindo do motor de voz local do DroidNote."""
        duration = len(samples) / float(sample_rate or 16_000)
        text, detected = self.transcribe_window(samples, sample_rate, language=language)
        return ([(0.0, duration, text)] if text else []), detected

    def test_key(self, api_key: str | None = None) -> tuple[bool, str]:
        key = (api_key if api_key is not None else self.api_key).strip()
        if not key:
            return False, "Informe uma chave da API OpenAI."
        try:
            with httpx.Client(timeout=15.0, verify=ssl_verify()) as client:
                response = client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
        except httpx.HTTPError as exc:
            return False, f"Não foi possível falar com a OpenAI: {exc}"
        if response.status_code == 200:
            return True, "Chave válida."
        return False, _error_detail(response)


def _language_fields(model: str, locked: str) -> dict[str, object]:
    """gpt-transcribe recebe `languages[]` (lista de códigos ISO 639-1) e recusa o `language`
    antigo junto; os outros modelos só conhecem `language`."""
    if model.startswith("gpt-transcribe"):
        return {"languages[]": [locked]}
    return {"language": locked}


def _detected_language(payload: object) -> str | None:
    """gpt-transcribe responde `languages: [{"code": "pt"}]`; lista vazia = não reconheceu."""
    if not isinstance(payload, dict):
        return None
    languages = payload.get("languages")
    if isinstance(languages, list):
        for item in languages:
            code = item.get("code") if isinstance(item, dict) else item
            resolved = _language_code(code)
            if resolved:
                return resolved
    return _language_code(payload.get("language"))


def samples_to_wav_bytes(samples: Sequence[float], sample_rate: int) -> bytes:
    audio = np.asarray(samples, dtype=np.float32)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


_LANGUAGE_NAMES = {
    "portuguese": "pt",
    "english": "en",
    "spanish": "es",
    "italian": "it",
    "german": "de",
    "french": "fr",
    "russian": "ru",
}


def _language_code(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return _LANGUAGE_NAMES.get(text, text[:5])


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
    return f"OpenAI recusou a transcrição (HTTP {response.status_code})."
