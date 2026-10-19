"""Detector de fala neural (Silero VAD) para a captura ao vivo.

O VAD por energia antigo tratava ventilador, teclado e música como fala e
cortava quem fala baixo. O Silero já vem dentro do faster-whisper (ONNX, ~2 MB),
então não há download novo. Se ele não carregar, volta para energia.
"""

from __future__ import annotations

import threading

import numpy as np

from app.core.logging import get_logger

log = get_logger("voice.vad")

FRAME = 512  # 32 ms a 16 kHz, o passo do Silero
START_PROB = 0.5
KEEP_PROB = 0.35
MIN_RMS = 0.0015


class SileroModel:
    """Carrega o Silero do faster-whisper uma vez por processo."""

    _instance: object | None = None
    _failed = False
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> object | None:
        if cls._instance is not None or cls._failed:
            return cls._instance
        with cls._lock:
            if cls._instance is not None or cls._failed:
                return cls._instance
            try:
                from faster_whisper.vad import get_vad_model

                cls._instance = get_vad_model()
                log.info("silero vad ready")
            except Exception as exc:
                cls._failed = True
                log.warning("silero vad unavailable, using energy gate: %s", exc)
        return cls._instance

    @classmethod
    def probabilities(cls, samples: np.ndarray) -> np.ndarray | None:
        model = cls.get()
        if model is None:
            return None
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return np.zeros(0, dtype=np.float32)
        remainder = audio.size % FRAME
        if remainder:
            audio = np.pad(audio, (0, FRAME - remainder))
        try:
            output = model(audio)  # type: ignore[operator]
        except Exception as exc:
            log.warning("silero vad failed: %s", exc)
            return None
        return np.asarray(output, dtype=np.float32).reshape(-1)


class StreamingVad:
    """Uma instância por canal. Recebe blocos de ~100 ms e devolve uma máscara de fala."""

    def __init__(self) -> None:
        self._tail = np.zeros(FRAME, dtype=np.float32)
        self._speaking = False
        self.last_prob = 0.0

    def mask(self, chunk: np.ndarray | list[float]) -> np.ndarray | None:
        """Máscara booleana por amostra do bloco, ou None se o Silero não estiver disponível."""
        audio = np.asarray(chunk, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return np.zeros(0, dtype=bool)
        # O último quadro do bloco anterior entra como contexto e a saída dele é descartada.
        joined = np.concatenate([self._tail, audio])
        probs = SileroModel.probabilities(joined)
        tail_source = joined[-FRAME:]
        self._tail = tail_source.copy()
        if probs is None:
            return None
        probs = probs[1:]
        frames = int(np.ceil(audio.size / FRAME))
        probs = probs[:frames]
        out = np.zeros(audio.size, dtype=bool)
        for index, prob in enumerate(probs):
            lo = index * FRAME
            hi = min(audio.size, lo + FRAME)
            frame = audio[lo:hi]
            loud = frame.size > 0 and float(np.sqrt(np.mean(frame * frame))) >= MIN_RMS
            if self._speaking:
                self._speaking = bool(prob >= KEEP_PROB)
            else:
                self._speaking = bool(prob >= START_PROB)
            out[lo:hi] = self._speaking and loud
        self.last_prob = float(probs[-1]) if probs.size else 0.0
        return out


def window_has_speech(samples: np.ndarray | list[float], *, min_ms: int = 240) -> bool | None:
    """Confere a janela inteira antes de gastar o Whisper. None = sem Silero."""
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    probs = SileroModel.probabilities(audio)
    if probs is None:
        return None
    frames_needed = max(1, int(min_ms / 32))
    return int(np.count_nonzero(probs >= START_PROB)) >= frames_needed
