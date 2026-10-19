from __future__ import annotations

from collections.abc import Callable, Sequence
import time

from app.domain.ports import AudioCallback


class FakeAudioCapture:
    def __init__(self) -> None:
        self.started = False
        self.mic_only = False
        self.callback: AudioCallback | None = None

    def list_devices(self) -> list[dict[str, str]]:
        return [
            {"id": "mic", "name": "Fake Mic", "kind": "microphone"},
            {"id": "loop", "name": "Fake Loopback", "kind": "loopback"},
        ]

    def start(
        self,
        callback: AudioCallback,
        *,
        microphone_id: str | None = None,
        loopback_id: str | None = None,
        mic_only: bool = False,
    ) -> None:
        self.started = True
        self.mic_only = mic_only
        self.callback = callback

    def stop(self) -> None:
        self.started = False

    def probe(self) -> dict[str, bool | str]:
        return {"microphone": True, "loopback": True, "supported": True, "message": "ok"}


class FakeAsr:
    def __init__(self, text: str = "olá mundo") -> None:
        self.text = text
        self.loaded = False
        self.downloaded = False
        self.model_size = "small"
        self.unload_calls = 0
        self.delay = 0.0
        self.ready = True

    def is_ready(self) -> bool:
        return self.ready

    def is_loaded(self) -> bool:
        return self.loaded

    def download(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        self.downloaded = True
        self.ready = True
        self.loaded = True
        if on_progress:
            on_progress(100, "ok")

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False
        self.unload_calls += 1

    def transcribe_window(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[str, str | None]:
        if self.delay:
            time.sleep(self.delay)
        return self.text, language or "pt"


class FakeVoiceEmbedder:
    """Embedder determinístico: o sinal médio do áudio escolhe a "voz"."""

    model_id = "fake-voice"
    dim = 8

    def __init__(self) -> None:
        import numpy as np

        self._np = np
        self.ready = True
        # Vozes ortogonais: pessoas diferentes ficam com cosseno zero.
        self.prototypes = list(np.eye(self.dim, dtype=np.float32)[:4])

    def is_ready(self) -> bool:
        return self.ready

    def embed(self, samples, sample_rate: int = 16_000):
        np = self._np
        audio = np.asarray(samples, dtype=np.float32)
        if audio.size < 9_600:
            return None
        index = int(abs(round(float(audio.mean()) * 10))) % len(self.prototypes)
        return self.prototypes[index].astype(np.float32)

    def embed_batch(self, features):
        return None


class FakeLlm:
    def __init__(self, payload: str | None = None) -> None:
        self.payload = payload or (
            '{"language":"pt","overview":"Reunião de teste.",'
            '"topics":[{"title":"Assunto A","points":["Ponto A"]}],'
            '"decisions":["Decisão B"],'
            '"action_items":[{"text":"Fazer C","owner":"Ana","due":"amanhã"}],'
            '"open_items":["Pendência D"]}'
        )
        self.model = "qwen2.5:3b"
        self.last_system: str | None = None

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        del prompt
        self.last_system = system
        return self.payload

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        self.last_system = system
        return f"Sobre: {prompt[:80]}"

    async def generate_text_stream(
        self,
        prompt: str,
        on_token,
        *,
        system: str | None = None,
    ) -> str:
        text = await self.generate_text(prompt, system=system)
        on_token(text)
        return text
