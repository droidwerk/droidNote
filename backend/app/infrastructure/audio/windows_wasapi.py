from __future__ import annotations

import threading
import time
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import numpy as np

from app.core.logging import get_logger
from app.domain.models import AudioChunk
from app.domain.ports import AudioCallback
from app.infrastructure.audio.resample import block_frames, candidate_rates, resample_mono

log = get_logger("audio.windows")

warnings.filterwarnings("ignore", message="data discontinuity in recording")

BLOCK_MS = 100
HEADSET_MARKERS = (
    "headphone",
    "headset",
    "hands-free",
    "handsfree",
    "earphone",
    "fone",
    "comunic",
    "bluetooth",
    "airpods",
    "jabra",
    "logitech",
    "wh-",
)


def _to_mono(frames: np.ndarray) -> np.ndarray:
    data = np.asarray(frames, dtype=np.float32)
    if data.ndim == 1:
        return data
    return data.mean(axis=1)


def names_match(left: str, right: str) -> bool:
    a = _normalize_name(left)
    b = _normalize_name(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _normalize_name(value: str) -> str:
    text = value.lower()
    for junk in (" (loopback)", " loopback", " (render)", " speaker", " speakers"):
        text = text.replace(junk, "")
    return " ".join(text.split())


def is_headset_name(name: str) -> bool:
    text = name.lower()
    return any(marker in text for marker in HEADSET_MARKERS)


@contextmanager
def open_input(device: object, preferred_hz: int, channels: int = 1) -> Iterator[tuple[object, int]]:
    last_error: Exception | None = None
    for rate in candidate_rates(preferred_hz):
        recorder = None
        entered = False
        try:
            recorder = device.recorder(samplerate=rate, channels=channels)  # type: ignore[attr-defined]
            stream = recorder.__enter__()
            entered = True
            probe = min(512, max(64, rate // 32))
            stream.record(numframes=probe)
            try:
                yield stream, rate
                return
            finally:
                recorder.__exit__(None, None, None)
        except Exception as exc:
            last_error = exc
            if recorder is not None and entered:
                try:
                    recorder.__exit__(None, None, None)
                except Exception:
                    pass
            continue
    raise RuntimeError(f"Nenhuma taxa de áudio funcionou neste dispositivo ({last_error})")


class _LatestLoopback:
    def __init__(self, device: object, stop: threading.Event, sample_rate: int) -> None:
        self._device = device
        self._stop = stop
        self._sample_rate = sample_rate
        self._lock = threading.Lock()
        self._buf = np.zeros(block_frames(sample_rate, BLOCK_MS), dtype=np.float32)
        self.alive = True
        self.thread = threading.Thread(target=self._run, name="droidnote-loopback", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with open_input(self._device, self._sample_rate) as (recorder, native_hz):
                    self.alive = True
                    native_block = block_frames(native_hz, BLOCK_MS)
                    while not self._stop.is_set():
                        frames = _to_mono(recorder.record(numframes=native_block))
                        resampled = resample_mono(frames, native_hz, self._sample_rate)
                        with self._lock:
                            self._buf = resampled
            except Exception as exc:
                self.alive = False
                if self._stop.is_set():
                    return
                log.warning("loopback reader retrying after %s", exc)
                time.sleep(0.4)

    def latest(self, count: int) -> np.ndarray:
        with self._lock:
            data = self._buf
        if data.size >= count:
            return data[:count]
        out = np.zeros(count, dtype=np.float32)
        out[: data.size] = data
        return out


class WindowsWasapiCapture:
    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mic_only = False
        self._warning: str | None = None
        self._error: str | None = None
        self._loopback_label: str | None = None

    def list_devices(self) -> list[dict[str, str]]:
        try:
            import soundcard as sc
        except Exception:
            return []
        default_speaker = sc.default_speaker()
        default_name = str(default_speaker.name) if default_speaker is not None else ""
        devices: list[dict[str, str]] = []
        for mic in sc.all_microphones():
            devices.append({"id": str(mic.id), "name": str(mic.name), "kind": "microphone", "recommended": "false"})
        for item in sc.all_microphones(include_loopback=True):
            if not getattr(item, "isloopback", False):
                continue
            recommended = names_match(str(item.name), default_name) or is_headset_name(str(item.name))
            devices.append(
                {
                    "id": str(item.id),
                    "name": str(item.name),
                    "kind": "loopback",
                    "recommended": "true" if recommended else "false",
                }
            )
        return devices

    def probe(self) -> dict[str, bool | str]:
        try:
            import soundcard as sc
        except Exception as exc:
            return {
                "microphone": False,
                "loopback": False,
                "supported": False,
                "message": f"Biblioteca de áudio indisponível: {exc}",
            }
        mics = sc.all_microphones()
        loopbacks = [item for item in sc.all_microphones(include_loopback=True) if getattr(item, "isloopback", False)]
        has_mic = len(mics) > 0
        has_loop = len(loopbacks) > 0 or len(sc.all_speakers()) > 0
        return {
            "microphone": has_mic,
            "loopback": has_loop,
            "supported": has_mic,
            "message": "ok" if has_mic else "Nenhum microfone encontrado.",
        }

    def start(
        self,
        callback: AudioCallback,
        *,
        microphone_id: str | None = None,
        loopback_id: str | None = None,
        mic_only: bool = False,
    ) -> None:
        self.stop()
        self._stop.clear()
        self._mic_only = mic_only
        self._warning = None
        self._error = None
        self._loopback_label = None
        self._thread = threading.Thread(
            target=self._run,
            args=(callback, microphone_id, loopback_id, mic_only),
            name="droidnote-wasapi",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

    @property
    def warning(self) -> str | None:
        return self._warning

    @property
    def loopback_label(self) -> str | None:
        return self._loopback_label

    def startup_error(self) -> str | None:
        if self._error:
            return self._error
        if self._thread is not None and not self._thread.is_alive() and not self._stop.is_set():
            return self._warning or "Captura de áudio encerrou sozinha."
        return None

    def _run(
        self,
        callback: Callable[[AudioChunk], None],
        microphone_id: str | None,
        loopback_id: str | None,
        mic_only: bool,
    ) -> None:
        try:
            import soundcard as sc
        except Exception:
            log.exception("soundcard import failed")
            self._error = "Biblioteca de áudio indisponível neste computador."
            return

        mic = _pick_microphone(sc, microphone_id)
        if mic is None:
            self._error = "Nenhum microfone disponível."
            log.error("no microphone available")
            return

        loopbacks = [] if mic_only else select_loopbacks(sc, loopback_id)
        if not loopbacks and not mic_only:
            self._warning = "Nenhuma saída da máquina encontrada — só o microfone."
        readers = [_LatestLoopback(item, self._stop, self.sample_rate) for item in loopbacks]
        if readers:
            self._loopback_label = " + ".join(str(item.name) for item in loopbacks)
            log.info("loopback devices: %s", self._loopback_label)
        timestamp_ms = 0
        try:
            while not self._stop.is_set():
                try:
                    with open_input(mic, self.sample_rate) as (mic_rec, mic_hz):
                        timestamp_ms = self._pump(mic_rec, mic_hz, readers, callback, timestamp_ms)
                except Exception as exc:
                    if self._stop.is_set():
                        break
                    log.warning("audio stream restarting after %s", exc)
                    time.sleep(0.4)
        except Exception:
            log.exception("capture loop failed")
            self._error = "Falha na captura WASAPI. Tente escolher a saída do fone ou só o microfone."
            self._warning = self._error
        finally:
            for reader in readers:
                reader.thread.join(timeout=1.0)

    def _pump(
        self,
        mic_rec: object,
        mic_hz: int,
        readers: list[_LatestLoopback],
        callback: Callable[[AudioChunk], None],
        timestamp_ms: int,
    ) -> int:
        mic_block = block_frames(mic_hz, BLOCK_MS)
        while not self._stop.is_set():
            try:
                mic_frames = resample_mono(
                    _to_mono(mic_rec.record(numframes=mic_block)),  # type: ignore[attr-defined]
                    mic_hz,
                    self.sample_rate,
                )
            except Exception as exc:
                log.warning("microphone read failed: %s", exc)
                raise
            mixed = np.asarray(mic_frames, dtype=np.float32)
            n = mixed.size
            if n == 0:
                continue
            loop_sum = np.zeros(n, dtype=np.float32)
            has_loop = False
            for reader in readers:
                if not reader.alive:
                    continue
                extra = reader.latest(n)
                loop_sum = loop_sum + extra[:n]
                has_loop = True
            mixed = np.clip(mixed + loop_sum, -1.0, 1.0)
            callback(
                AudioChunk(
                    samples=mixed.tolist(),
                    sample_rate=self.sample_rate,
                    timestamp_ms=timestamp_ms,
                    mic=np.clip(mic_frames, -1.0, 1.0).tolist(),
                    loopback=np.clip(loop_sum, -1.0, 1.0).tolist() if has_loop else None,
                )
            )
            timestamp_ms += int(n * 1000 / self.sample_rate)
        return timestamp_ms


def _pick_microphone(sc: object, microphone_id: str | None) -> object | None:
    mics = list(sc.all_microphones())  # type: ignore[attr-defined]
    if microphone_id:
        for mic in mics:
            if str(mic.id) == microphone_id or names_match(str(mic.name), microphone_id):
                return mic
    return sc.default_microphone()  # type: ignore[attr-defined]


def select_loopbacks(sc: object, loopback_id: str | None) -> list[object]:
    candidates = [
        item
        for item in sc.all_microphones(include_loopback=True)  # type: ignore[attr-defined]
        if getattr(item, "isloopback", False)
    ]
    if loopback_id:
        picked = _match_loopback(sc, candidates, loopback_id)
        return [picked] if picked is not None else []

    chosen: list[object] = []
    seen: set[str] = set()

    def add(item: object | None) -> None:
        if item is None:
            return
        key = str(getattr(item, "id", getattr(item, "name", item)))
        if key in seen:
            return
        seen.add(key)
        chosen.append(item)

    default_speaker = sc.default_speaker()  # type: ignore[attr-defined]
    add(loopback_for_speaker(sc, default_speaker))
    if default_speaker is not None:
        for item in candidates:
            if names_match(str(item.name), str(default_speaker.name)):
                add(item)

    for speaker in sc.all_speakers():  # type: ignore[attr-defined]
        if is_headset_name(str(speaker.name)):
            add(loopback_for_speaker(sc, speaker))
    for item in candidates:
        if is_headset_name(str(item.name)):
            add(item)

    if chosen:
        return chosen
    return candidates


def _match_loopback(sc: object, candidates: list[object], loopback_id: str) -> object | None:
    for item in candidates:
        if str(getattr(item, "id", "")) == loopback_id or names_match(str(item.name), loopback_id):
            return item
    for speaker in sc.all_speakers():  # type: ignore[attr-defined]
        if str(speaker.id) == loopback_id or names_match(str(speaker.name), loopback_id):
            return loopback_for_speaker(sc, speaker)
    return None


def loopback_for_speaker(sc: object, speaker: object | None) -> object | None:
    if speaker is None:
        return None
    for token in (str(speaker.name), str(getattr(speaker, "id", ""))):
        if not token:
            continue
        try:
            mic = sc.get_microphone(id=token, include_loopback=True)  # type: ignore[attr-defined]
            if mic is not None and getattr(mic, "isloopback", True):
                return mic
        except Exception:
            continue
    for item in sc.all_microphones(include_loopback=True):  # type: ignore[attr-defined]
        if getattr(item, "isloopback", False) and names_match(str(item.name), str(speaker.name)):
            return item
    return None
