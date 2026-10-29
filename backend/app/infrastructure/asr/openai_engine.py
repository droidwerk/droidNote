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
# Preços por minuto de áudio (tabela da OpenAI): mini US$ 0,003; os demais US$ 0,006.
# A interface traduz nome e explicação (models.* e modelHelp.*); aqui fica o nome curto de reserva.
CLOUD_ASR_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-4o-mini-transcribe", "GPT-4o mini Transcribe — recomendado"),
    ("gpt-4o-mini-transcribe-2025-12-15", "GPT-4o mini Transcribe (dez/2025)"),
    ("gpt-4o-transcribe", "GPT-4o Transcribe"),
    ("gpt-4o-transcribe-diarize", "GPT-4o Transcribe Diarize"),
    ("whisper-1", "Whisper 1"),
)
CLOUD_MODELS = CLOUD_ASR_MODELS


class OpenAIWhisperEngine:
    def __init__(self, api_key: str = "", model: str = "whisper-1") -> None:
        self.api_key = api_key
        self.model = model
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
        data: dict[str, str] = {"model": self.model}
        prompt = build_asr_prompt(locked)
        if prompt:
            data["prompt"] = prompt
        if locked:
            data["language"] = locked
        if "diarize" in self.model:
            # O modelo com diarização só responde neste formato; o texto vem por segmento.
            data["response_format"] = "diarized_json"
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
        return text, locked or None

    def transcribe_words(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[list[tuple[float, float, str]], str | None]:
        """Palavras com tempo. Só o whisper-1 devolve timestamps; os modelos
        gpt-4o-* devolvem o texto da janela inteira como um trecho só."""
        duration = len(samples) / float(sample_rate or 16_000)
        if "diarize" in self.model:
            return self._transcribe_diarized(samples, sample_rate, language=language)
        if self.model != "whisper-1":
            text, detected = self.transcribe_window(samples, sample_rate, language=language)
            return ([(0.0, duration, text)] if text else []), detected
        self.load()
        locked = whisper_language_arg(language)
        wav = samples_to_wav_bytes(samples, sample_rate)
        data: dict[str, object] = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        if locked:
            data["language"] = locked
        with httpx.Client(timeout=60.0, verify=ssl_verify()) as client:
            response = client.post(
                OPENAI_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                data=data,
                files={"file": ("audio.wav", wav, "audio/wav")},
            )
        if response.status_code >= 400:
            log.warning("openai transcribe failed status=%s", response.status_code)
            raise RuntimeError(_error_detail(response))
        payload = response.json()
        detected = locked or _language_code(payload.get("language"))
        words: list[tuple[float, float, str]] = []
        for segment in payload.get("segments") or []:
            text = filter_transcript(str(segment.get("text") or ""), locked)
            if not text:
                continue
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or start)
            inside = [
                item
                for item in payload.get("words") or []
                if start - 0.05 <= float(item.get("start") or 0.0) < end + 0.05
            ]
            if inside:
                for item in inside:
                    token = str(item.get("word") or "").strip()
                    if token:
                        w_start = float(item.get("start") or start)
                        words.append((w_start, max(float(item.get("end") or w_start), w_start), token))
            else:
                words.append((start, max(end, start), text))
        if not words:
            text = filter_transcript(str(payload.get("text") or ""), locked)
            if text:
                words.append((0.0, duration, text))
        return words, detected

    def _transcribe_diarized(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[list[tuple[float, float, str]], str | None]:
        """Modelo com diarização: cada trecho de um falante volta com início e fim dentro da janela.

        Só os cortes entram no fluxo — como "palavras" com tempo — para o motor de voz do DroidNote
        separar a janela por quem falou. O rótulo "speaker A/B" da OpenAI é descartado: quem diz
        quem é cada voz (e dá nome a ela) continua sendo a impressão vocal guardada neste PC.
        """
        self.load()
        locked = whisper_language_arg(language)
        wav = samples_to_wav_bytes(samples, sample_rate)
        duration = len(samples) / float(sample_rate or 16_000)
        data: dict[str, str] = {"model": self.model, "response_format": "diarized_json"}
        if locked:
            data["language"] = locked
        with httpx.Client(timeout=60.0, verify=ssl_verify()) as client:
            response = client.post(
                OPENAI_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                data=data,
                files={"file": ("audio.wav", wav, "audio/wav")},
            )
        if response.status_code >= 400:
            log.warning("openai transcribe failed status=%s", response.status_code)
            raise RuntimeError(_error_detail(response))
        payload = response.json()
        pieces: list[tuple[float, float, str]] = []
        for segment in payload.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            text = filter_transcript(str(segment.get("text") or ""), locked)
            if not text:
                continue
            start = max(0.0, float(segment.get("start") or 0.0))
            end = max(start, min(duration, float(segment.get("end") or start)))
            pieces.append((start, end, text))
        if not pieces:
            text = filter_transcript(str(payload.get("text") or ""), locked)
            if text:
                pieces.append((0.0, duration, text))
        return pieces, locked or None

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
