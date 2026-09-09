from __future__ import annotations

import json
import re
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from app.core.logging import get_logger

log = get_logger("asr")

_REPEAT = re.compile(r"\b(\w{1,12})(?:[\s,.\-]+\1){4,}\b", re.IGNORECASE)
_HUM = re.compile(
    r"^\s*(hum|hã|hãm|uh|uhum|mm+|mhm)([,\s.]+(hum|hã|hãm|uh|uhum|mm+|mhm))+\s*$",
    re.IGNORECASE,
)
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_CJK = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")

# Frases que o Whisper cospe em trechos de silêncio ou música, herdadas do
# YouTube no material de treino. Nunca foram ditas na reunião.
_PROMPT_ECHO = re.compile(
    r"(do not invent phrases that were not said"
    r"|não invente frases que não foram ditas"
    r"|no invente frases que no se dijeron)",
    re.IGNORECASE,
)
_HALLUCINATION = re.compile(
    r"(inscreva-se\s+no\s+canal"
    r"|ative\s+o\s+sininho"
    r"|deixe\s+seu\s+like"
    r"|não\s+esqueça\s+de\s+se\s+inscrever"
    r"|legendas?\s+(pela|por|feitas?\s+por)"
    r"|subtitles?\s+by"
    r"|amara\.org"
    r"|transcri(ção|ption)\s+(por|by)\s"
    r"|obrigado\s+por\s+assistir"
    r"|thanks?\s+for\s+watching"
    r"|like\s+and\s+subscribe)",
    re.IGNORECASE,
)

LANGUAGE_LABELS = {
    "pt": "português brasileiro",
    "en": "English",
    "es": "español",
}


def build_asr_prompt(language: str | None) -> str:
    if language == "pt":
        return "Transcreva em português brasileiro."
    if language == "es":
        return "Transcribe en español."
    if language == "en":
        return "Transcribe in English."
    return ""


def filter_transcript(text: str, language: str | None = None) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if _HUM.match(cleaned):
        return ""
    if _REPEAT.search(cleaned):
        return ""
    if _HALLUCINATION.search(cleaned):
        return ""
    if _PROMPT_ECHO.search(cleaned):
        return ""
    locked = language if language and language != "auto" else None
    if locked in {"pt", "en", "es"}:
        if _CYRILLIC.search(cleaned) or _CJK.search(cleaned):
            return ""
    return cleaned


def whisper_language_arg(language: str | None) -> str | None:
    if not language or language == "auto":
        return None
    return language


WHISPER_CATALOG: tuple[tuple[str, str], ...] = (
    ("tiny", "Tiny — mais rápido, menos preciso"),
    ("base", "Base"),
    ("small", "Small — recomendado para CPU"),
    ("medium", "Medium"),
    ("large-v3", "Large v3 — preciso, lento na CPU"),
    ("large-v3-turbo", "Large v3 Turbo — recomendado para GPU"),
    ("distil-large-v3", "Distil Large v3"),
)


def detect_installed_whisper(models_dir: Path) -> set[str]:
    found: set[str] = set()
    if not models_dir.exists():
        return found
    blobs = [str(path).lower().replace("\\", "/") for path in models_dir.rglob("model.bin")]
    catalog_ids = sorted((item[0] for item in WHISPER_CATALOG), key=len, reverse=True)
    for blob in blobs:
        for model_id in catalog_ids:
            if model_id.lower() in blob:
                found.add(model_id)
                break
    return found


def catalog_whisper_models(models_dir: Path, current: str) -> list[dict[str, str | bool]]:
    installed = detect_installed_whisper(models_dir)
    sizes = _installed_sizes(models_dir)
    rows: list[dict[str, str | bool]] = []
    seen: set[str] = set()
    for model_id, label in WHISPER_CATALOG:
        seen.add(model_id)
        present = model_id in installed
        size_label = sizes.get(model_id, "")
        detail = size_label if present and size_label else ""
        rows.append(
            {
                "id": model_id,
                "label": label,
                "installed": present,
                "source": "whisper",
                "detail": detail,
                "recommended": "recomendado" in label.lower(),
            }
        )
    if current and current not in seen:
        present = current in installed
        rows.append(
            {
                "id": current,
                "label": current,
                "installed": present,
                "source": "whisper",
                "detail": sizes.get(current, "") if present else "",
            }
        )
    return rows


class WhisperEngine:
    def __init__(self, model_size: str, models_dir: Path, device_policy: str = "auto") -> None:
        self.model_size = model_size
        self.models_dir = models_dir
        self.device_policy = (device_policy or "auto").lower().strip()
        self._model: object | None = None
        self._force_cpu = False
        self._device = "cpu"
        self._load_lock = threading.Lock()

    def is_ready(self) -> bool:
        if self._model is not None:
            return True
        return self._complete_marker().is_file()

    def is_loaded(self) -> bool:
        return self._model is not None

    def _complete_marker(self) -> Path:
        safe = self.model_size.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.models_dir / ".complete" / f"{safe}.ok"

    def _mark_complete(self) -> None:
        path = self._complete_marker()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")

    @property
    def device(self) -> str:
        return self._device

    def download(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        if not _whisper_importable():
            raise RuntimeError(
                "O motor de transcrição (faster-whisper) não está instalado. Reinstale o DroidNote."
            )
        if self._complete_marker().is_file():
            if on_progress:
                on_progress(92, "Conferindo o modelo…")
            self.load()
            if on_progress:
                on_progress(100, "Modelo de transcrição pronto")
            return
        if self.model_size in detect_installed_whisper(self.models_dir):
            if on_progress:
                on_progress(92, "Conferindo o modelo já baixado…")
            try:
                self.load()
                if on_progress:
                    on_progress(100, "Modelo de transcrição pronto")
                return
            except Exception:
                log.warning("whisper files present but invalid; downloading again size=%s", self.model_size)
        if on_progress:
            on_progress(4, "Baixando o modelo Whisper…")
        _download_with_progress(self.model_size, self.models_dir, on_progress)
        if on_progress:
            on_progress(92, "Conferindo o modelo…")
        self.load()
        if on_progress:
            on_progress(100, "Modelo de transcrição pronto")

    def load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if not _whisper_importable():
                raise RuntimeError(
                    "O motor de transcrição (faster-whisper) não está instalado. Reinstale o DroidNote."
                )
            device, compute = self._pick_device()
            self.models_dir.mkdir(parents=True, exist_ok=True)
            started = time.perf_counter()
            log.info(
                "loading whisper model size=%s device=%s policy=%s",
                self.model_size,
                device,
                self.device_policy,
            )
            try:
                self._model = self._create_model(device, compute)
                self._device = device
                self._warmup()
            except Exception as exc:
                if device == "cpu":
                    raise
                log.warning("cuda whisper unavailable (%s); using cpu so any Windows PC can run", exc)
                self._remember_cpu(str(exc)[:240])
                self._model = self._create_model("cpu", "int8")
                self._device = "cpu"
                self._warmup()
            self._mark_complete()
            log.info(
                "whisper loaded size=%s device=%s in %.1fs",
                self.model_size,
                self._device,
                time.perf_counter() - started,
            )

    def unload(self) -> None:
        self._model = None
        log.info("whisper unloaded")

    def transcribe_window(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[str, str | None]:
        import numpy as np

        self.load()
        audio = np.asarray(samples, dtype=np.float32)
        try:
            return self._decode(audio, language=language)
        except Exception as exc:
            if self._device != "cuda" or not _is_cuda_runtime_error(exc):
                raise
            log.warning("cuda whisper failed (%s); falling back to cpu", exc)
            self._remember_cpu(str(exc)[:240])
            self._model = None
            self.load()
            return self._decode(audio, language=language)

    def _pick_device(self) -> tuple[str, str]:
        return _select_device(self.device_policy, force_cpu=self._force_cpu or self._cached_cpu())

    def _create_model(self, device: str, compute: str) -> object:
        from faster_whisper import WhisperModel

        if device != "cpu":
            return WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute,
                download_root=str(self.models_dir),
            )
        last_error: Exception | None = None
        for ctype in (compute, "int8", "int8_float32", "float32"):
            try:
                return WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type=ctype,
                    download_root=str(self.models_dir),
                )
            except Exception as exc:
                last_error = exc
                log.warning("cpu compute_type=%s failed: %s", ctype, exc)
        if last_error:
            raise last_error
        raise RuntimeError("Não foi possível carregar o Whisper na CPU")

    def _warmup(self) -> None:
        import numpy as np

        self._decode(np.zeros(16_000, dtype=np.float32), language=None)

    def _cache_path(self) -> Path:
        return self.models_dir / "whisper-compute.json"

    def _remember_cpu(self, reason: str) -> None:
        self._force_cpu = True
        try:
            self._cache_path().write_text(
                json.dumps({"device": "cpu", "reason": reason}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def clear_cpu_cache(self) -> None:
        self._force_cpu = False
        try:
            self._cache_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _cached_cpu(self) -> bool:
        if self.device_policy == "cuda":
            return False
        path = self._cache_path()
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return payload.get("device") == "cpu"

    def _decode(
        self,
        audio: object,
        *,
        language: str | None,
    ) -> tuple[str, str | None]:
        model = self._model
        if model is None:
            return "", None
        locked = whisper_language_arg(language)
        prompt = build_asr_prompt(locked)
        beam_size = 1 if self._device == "cpu" else 3
        segments, info = model.transcribe(  # type: ignore[union-attr]
            audio,
            language=locked,
            vad_filter=False,
            beam_size=beam_size,
            temperature=0,
            without_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
        )
        texts: list[str] = []
        detected: str | None = getattr(info, "language", None)
        for segment in segments:
            piece = (segment.text or "").strip()
            if piece:
                texts.append(piece)
        joined = filter_transcript(" ".join(texts).strip(), locked)
        return joined, locked or detected


def _whisper_importable() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _select_device(policy: str = "auto", force_cpu: bool = False) -> tuple[str, str]:
    normalized = (policy or "auto").lower().strip()
    if force_cpu or normalized == "cpu":
        return "cpu", "int8"
    if normalized == "cuda":
        if _cuda_usable():
            return "cuda", "float16"
        log.warning("CUDA pedido, mas o runtime (cuBLAS) não está completo neste Windows; usando CPU")
        return "cpu", "int8"
    if _cuda_usable():
        return "cuda", "float16"
    return "cpu", "int8"


def _cuda_usable() -> bool:
    if not _cublas_available():
        return False
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _cublas_available() -> bool:
    if sys.platform != "win32":
        return True
    import ctypes

    for name in ("cublas64_12.dll", "cublas64_13.dll", "cublas64_11.dll"):
        try:
            ctypes.WinDLL(name)
            return True
        except OSError:
            continue
    return False


def _is_cuda_runtime_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("cublas", "cudnn", "cublas64", "cuda"))


def _format_bytes(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f} GB"
    if size >= 1024**2:
        return f"{size / 1024**2:.0f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _installed_sizes(models_dir: Path) -> dict[str, str]:
    sizes: dict[str, str] = {}
    if not models_dir.exists():
        return sizes
    catalog_ids = sorted((item[0] for item in WHISPER_CATALOG), key=len, reverse=True)
    for blob in models_dir.rglob("model.bin"):
        text = str(blob).lower().replace("\\", "/")
        for model_id in catalog_ids:
            if model_id.lower() in text:
                sizes[model_id] = _format_bytes(_dir_bytes(blob.parent))
                break
    return sizes


def _download_with_progress(
    model_size: str,
    models_dir: Path,
    on_progress: Callable[[int, str], None] | None,
) -> None:
    from faster_whisper.utils import download_model

    models_dir.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    baseline = _dir_bytes(models_dir)

    def poll() -> None:
        while not stop.wait(0.6):
            if not on_progress:
                return
            grown = max(0, _dir_bytes(models_dir) - baseline)
            mb = grown / (1024 * 1024)
            pct = min(88, 8 + int(mb / 18))
            on_progress(pct, f"Baixando Whisper… {mb:.0f} MB")

    watcher = threading.Thread(target=poll, daemon=True, name="droidnote-whisper-dl")
    if on_progress:
        watcher.start()
    try:
        try:
            import huggingface_hub

            tqdm_cls = _progress_tqdm(on_progress)
            original = huggingface_hub.snapshot_download

            def wrapped(*args, **kwargs):
                if tqdm_cls is not None:
                    kwargs.setdefault("tqdm_class", tqdm_cls)
                return original(*args, **kwargs)

            huggingface_hub.snapshot_download = wrapped  # type: ignore[method-assign]
            try:
                download_model(model_size, output_dir=str(models_dir), cache_dir=str(models_dir))
            finally:
                huggingface_hub.snapshot_download = original  # type: ignore[method-assign]
        except TypeError:
            download_model(model_size, output_dir=str(models_dir))
    finally:
        stop.set()


def _progress_tqdm(on_progress: Callable[[int, str], None] | None):
    if on_progress is None:
        return None
    try:
        from tqdm.auto import tqdm as StdTqdm
    except Exception:
        return None

    class _Tqdm(StdTqdm):
        def update(self, n=1):
            done = super().update(n)
            total = float(self.total or 0)
            if total > 0:
                frac = min(1.0, self.n / total)
                mb = self.n / (1024 * 1024)
                on_progress(min(90, 8 + int(frac * 82)), f"Baixando Whisper… {mb:.0f} MB")
            return done

    return _Tqdm

