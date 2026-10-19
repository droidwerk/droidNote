"""Impressão vocal neural (speaker embedding) rodando neste PC.

Modelo: WeSpeaker ResNet34-LM (VoxCeleb), exportado em ONNX. 26 MB, roda na CPU
em ~10 ms por segundo de fala. O arquivo é baixado uma vez e conferido por
SHA-256; o build do instalador pode embuti-lo em `resources/voice/`.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.logging import get_logger
from app.infrastructure.voice.fbank import cmn, fbank

log = get_logger("voice.embedder")

MIN_SECONDS = 0.6


@dataclass(frozen=True)
class VoiceModel:
    id: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    window: str
    scale: float
    dim: int


VOICE_MODEL = VoiceModel(
    id="wespeaker-resnet34-lm",
    filename="wespeaker_resnet34_lm.onnx",
    url=(
        "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/"
        "resolve/main/voxceleb_resnet34_LM.onnx"
    ),
    sha256="7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068",
    size_bytes=26_530_309,
    window="hamming",
    scale=32768.0,
    dim=256,
)


def normalize(vector: np.ndarray) -> np.ndarray:
    data = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(data))
    if not np.isfinite(norm) or norm <= 1e-8:
        return data
    return data / norm


class OnnxVoiceEmbedder:
    def __init__(self, models_dir: Path, model: VoiceModel = VOICE_MODEL) -> None:
        self.models_dir = models_dir
        self.model = model
        self._session: object | None = None
        self._input = "feats"
        self._lock = threading.Lock()
        self._load_error: str | None = None

    @property
    def model_id(self) -> str:
        return self.model.id

    @property
    def dim(self) -> int:
        return self.model.dim

    @property
    def target_path(self) -> Path:
        return self.models_dir / "voice" / self.model.filename

    def candidates(self) -> list[Path]:
        paths: list[Path] = []
        override = os.environ.get("DROIDNOTE_VOICE_MODEL")
        if override:
            paths.append(Path(override))
        paths.append(self.target_path)
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            paths.append(Path(bundle) / "voice" / self.model.filename)
        exe_dir = Path(sys.executable).resolve().parent
        paths.append(exe_dir / "voice" / self.model.filename)
        return paths

    def model_path(self) -> Path | None:
        for path in self.candidates():
            try:
                if path.is_file() and path.stat().st_size > 1_000_000:
                    return path
            except OSError:
                continue
        return None

    def is_ready(self) -> bool:
        return self._load_error is None and self.model_path() is not None

    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load(self) -> None:
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return
            path = self.model_path()
            if path is None:
                raise RuntimeError("Motor de voz ainda não foi baixado.")
            import onnxruntime as ort

            options = ort.SessionOptions()
            # A CPU é dividida com o Whisper: dois threads bastam para o modelo de voz.
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            started = time.perf_counter()
            try:
                session = ort.InferenceSession(
                    str(path), sess_options=options, providers=["CPUExecutionProvider"]
                )
            except Exception as exc:
                self._load_error = str(exc)[:240]
                raise
            self._input = session.get_inputs()[0].name
            self._session = session
            log.info("voice model loaded path=%s in %.2fs", path, time.perf_counter() - started)

    def embed(self, samples: Sequence[float] | np.ndarray, sample_rate: int = 16_000) -> np.ndarray | None:
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if sample_rate != 16_000 or audio.size < int(MIN_SECONDS * 16_000):
            return None
        if self._session is None:
            try:
                self.load()
            except Exception:
                log.exception("voice model load failed")
                return None
        features = cmn(fbank(audio, window=self.model.window, scale=self.model.scale))
        if features.shape[0] < 20:
            return None
        session = self._session
        if session is None:
            return None
        output = session.run(None, {self._input: features[None, :, :]})  # type: ignore[attr-defined]
        vector = normalize(np.asarray(output[0], dtype=np.float32)[0])
        if not np.all(np.isfinite(vector)):
            return None
        return vector

    def embed_batch(self, features: np.ndarray) -> np.ndarray | None:
        """Lote de features já normalizadas (B, T, 80) -> (B, dim) unitários."""
        if self._session is None:
            try:
                self.load()
            except Exception:
                log.exception("voice model load failed")
                return None
        session = self._session
        if session is None or features.ndim != 3 or features.shape[0] == 0:
            return None
        output = session.run(None, {self._input: features.astype(np.float32)})  # type: ignore[attr-defined]
        vectors = np.asarray(output[0], dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.maximum(norms, 1e-8)
        if not np.all(np.isfinite(vectors)):
            return None
        return vectors

    def download(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        if self.model_path() is not None:
            if on_progress:
                on_progress(100, "Motor de voz pronto")
            return
        import httpx

        from app.core.net_tls import ssl_verify

        target = self.target_path
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part")
        digest = hashlib.sha256()
        received = 0
        total = self.model.size_bytes
        if on_progress:
            on_progress(2, "Baixando motor de voz…")
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=20.0), follow_redirects=True, verify=ssl_verify()) as client:
            with client.stream("GET", self.model.url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or total) or total
                with partial.open("wb") as handle:
                    for block in response.iter_bytes(1 << 16):
                        handle.write(block)
                        digest.update(block)
                        received += len(block)
                        if on_progress and total:
                            pct = min(96, 2 + int(received * 94 / total))
                            on_progress(pct, f"Baixando motor de voz… {received / 1_048_576:.0f} MB")
        if digest.hexdigest() != self.model.sha256:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                "O arquivo do motor de voz chegou corrompido ou adulterado e foi descartado."
            )
        os.replace(partial, target)
        self._load_error = None
        if on_progress:
            on_progress(100, "Motor de voz pronto")
        log.info("voice model downloaded path=%s", target)

    def status(self) -> dict[str, object]:
        path = self.model_path()
        return {
            "ready": path is not None and self._load_error is None,
            "loaded": self.is_loaded(),
            "model": self.model.id,
            "path": str(path) if path else "",
            "size_mb": round(self.model.size_bytes / 1_048_576, 1),
            "error": self._load_error or "",
        }


def verify_file(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest() == expected
