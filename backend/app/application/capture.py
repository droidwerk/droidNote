from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.application.bus import EventBus
from app.core.config import Settings, session_recording_path
from app.core.logging import get_logger
from app.domain.models import AudioChunk, Person, Session, TranscriptSegment
from app.domain.ports import AudioCapturePort, AsrPort, SessionRepository
from app.infrastructure.asr.overlap import strip_overlap
from app.infrastructure.asr.scene import annotate_transcript
from app.infrastructure.asr.vad import SpeechBuffer, chunk_monitor, has_speech
from app.infrastructure.audio.wav_writer import SessionWavWriter
from app.infrastructure.audio.windows_wasapi import WindowsWasapiCapture
from app.infrastructure.persistence.sqlite import new_id

log = get_logger("capture")

START_AUDIO_GRACE = 0.35
LEVEL_EVERY = 0.08
PendingWindow = tuple[list[float], int, int, str, str]


@dataclass
class CaptureState:
    recording: bool = False
    session_id: str | None = None
    mic_only: bool = False
    warning: str | None = None
    phase: str = "idle"
    loopback_name: str | None = None
    started_at: datetime | None = None


class CaptureService:
    def __init__(
        self,
        settings: Settings,
        audio: AudioCapturePort,
        asr: AsrPort,
        store: SessionRepository,
        bus: EventBus,
    ) -> None:
        self._settings = settings
        self._audio = audio
        self._asr = asr
        self._store = store
        self._bus = bus
        self.state = CaptureState()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mic_buf = self._new_buffer()
        self._loop_buf = self._new_buffer()
        self._pending: asyncio.Queue[PendingWindow] = asyncio.Queue()
        self._worker_lock = asyncio.Lock()
        self._worker_task: asyncio.Task[None] | None = None
        self._last_level_emit = 0.0
        self._transcribing = False
        self._people: list[Person] = []
        self._self_person_id: str | None = None
        self._last_text: dict[str, str] = {}
        self._writer: SessionWavWriter | None = None
        self._drain_events: dict[str, asyncio.Event] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def list_devices(self) -> list[dict[str, str]]:
        return self._audio.list_devices()

    def is_recording(self) -> bool:
        return self.state.recording

    def whisper_loaded(self) -> bool:
        return bool(getattr(self._asr, "is_loaded", lambda: False)())

    @property
    def asr_device(self) -> str:
        return str(getattr(self._asr, "device", "cpu"))

    def _new_buffer(self) -> SpeechBuffer:
        return SpeechBuffer(
            self._settings.sample_rate,
            min_ms=600,
            max_ms=int(self._settings.window_seconds * 1000),
            silence_ms=400,
            overlap_ms=int(self._settings.overlap_seconds * 1000),
        )

    async def start(
        self,
        *,
        microphone_id: str | None = None,
        loopback_id: str | None = None,
        mic_only: bool = False,
        title: str | None = None,
        participant_ids: list[str] | None = None,
        capture_mode: str = "meeting",
    ) -> CaptureState:
        if self.state.recording:
            return self.state
        if not self._asr.is_ready() and not hasattr(self._asr, "load"):
            raise RuntimeError("Modelo de transcrição ainda não está pronto")

        mode = _normalize_mode(capture_mode)
        session = Session(
            id=new_id(),
            title=title or _default_title(mode),
            started_at=datetime.now(tz=UTC),
            ended_at=None,
            status="recording",
            language=_locked_language(self._settings.language),
            capture_mode=mode,
        )
        await self._store.create_session(session)
        self._people = []
        saved_self = await self._store.get_setting("self_person_id")
        self._self_person_id = saved_self or None
        self._last_text = {}
        await self.set_participants(session.id, participant_ids or [])
        self._mic_buf = self._new_buffer()
        self._loop_buf = self._new_buffer()
        self._pending = asyncio.Queue()
        self._transcribing = False
        if await self._should_save_recordings():
            self._open_writer(session.id)
        else:
            self._close_writer()
        self._worker_task = asyncio.create_task(self._consume_windows(self._pending))
        self.state = CaptureState(
            recording=True,
            session_id=session.id,
            mic_only=mic_only,
            phase="loading",
            started_at=session.started_at,
        )
        await self._bus.publish(_capture_event(self.state))
        try:
            self._audio.start(
                self._on_chunk,
                microphone_id=microphone_id,
                loopback_id=loopback_id,
                mic_only=mic_only,
            )
            await asyncio.sleep(START_AUDIO_GRACE)
            audio_error = _audio_startup_error(self._audio)
            if audio_error:
                raise RuntimeError(audio_error)
            await asyncio.to_thread(self._asr.load)
            warning = getattr(self._audio, "warning", None)
            loopback_name = getattr(self._audio, "loopback_label", None)
            if isinstance(self._audio, WindowsWasapiCapture):
                warning = self._audio.warning
                loopback_name = self._audio.loopback_label
            if not mic_only and not loopback_name and not warning:
                warning = "Saída da máquina não entrou. Escolha o fone em 'Áudio do sistema'."
            self.state = CaptureState(
                recording=True,
                session_id=session.id,
                mic_only=mic_only,
                warning=warning if isinstance(warning, str) else None,
                phase="listening",
                loopback_name=loopback_name if isinstance(loopback_name, str) else None,
                started_at=session.started_at,
            )
            await self._bus.publish(_capture_event(self.state))
            log.info("capture started session=%s mic_only=%s", session.id, mic_only)
            return self.state
        except Exception:
            await self._abort_start(session.id, mic_only)
            raise

    async def stop(self) -> CaptureState:
        if not self.state.recording or not self.state.session_id:
            return self.state
        session_id = self.state.session_id
        mic_only = self.state.mic_only
        pending = self._pending
        worker = self._worker_task
        self._worker_task = None
        self.state = CaptureState(
            recording=False, session_id=session_id, mic_only=mic_only, phase="idle"
        )
        await self._bus.publish(_capture_event(self.state))
        await asyncio.to_thread(self._audio.stop)
        await asyncio.sleep(0)
        self._enqueue_leftovers(session_id, pending)
        # Whisper stays loaded so the next recording does not wait on model load.
        self._close_writer()
        session = await self._store.get_session(session_id)
        if session:
            locked = _locked_language(self._settings.language)
            if locked:
                primary = locked
            else:
                languages = await self._store.list_segments(session_id)
                primary = _majority_language([item.language for item in languages])
            await self._store.update_session(
                replace(
                    session,
                    ended_at=datetime.now(tz=UTC),
                    status="stopped",
                    language=primary,
                )
            )
        done = asyncio.Event()
        self._drain_events[session_id] = done
        asyncio.create_task(self._drain_after_stop(session_id, pending, worker, done))
        log.info("capture stopped session=%s", session_id)
        return self.state

    async def wait_drain(self, session_id: str, timeout: float | None = None) -> None:
        event = self._drain_events.get(session_id)
        if event is None:
            return
        if timeout is None:
            await event.wait()
            return
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            log.warning("drain wait timed out session=%s", session_id)

    async def wait_all_drains(self, timeout: float = 30.0) -> None:
        events = list(self._drain_events.values())
        for event in events:
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except TimeoutError:
                pass

    async def set_participants(self, session_id: str, person_ids: list[str]) -> list[str]:
        people = await self._store.list_people_by_ids(person_ids)
        await self._store.set_session_participants(session_id, [item.id for item in people])
        self._people = people
        if not self._self_person_id and len(people) == 1:
            self._self_person_id = people[0].id
        elif self._self_person_id and self._self_person_id not in {item.id for item in people}:
            if len(people) == 1:
                self._self_person_id = people[0].id
        return [item.name for item in people]

    def note_speaker(self, speaker_id: str | None, source: str | None = None) -> None:
        if not self.state.recording:
            return
        if source in (None, "mic") and speaker_id:
            self._self_person_id = speaker_id

    def set_self_person(self, person_id: str | None) -> None:
        self._self_person_id = person_id or None

    async def _should_save_recordings(self) -> bool:
        stored = await self._store.get_setting("save_recordings")
        if stored is None:
            return True
        return stored != "0"

    def _open_writer(self, session_id: str) -> None:
        self._close_writer()
        try:
            path = session_recording_path(self._settings, session_id)
            self._writer = SessionWavWriter(path, self._settings.sample_rate)
        except Exception:
            log.exception("wav open failed session=%s", session_id)
            self._writer = None

    def _close_writer(self) -> None:
        writer = self._writer
        self._writer = None
        if writer is None:
            return
        try:
            writer.close()
        except Exception:
            log.exception("wav close failed")

    async def _abort_start(self, session_id: str, mic_only: bool) -> None:
        self.state = CaptureState(
            recording=False, session_id=session_id, mic_only=mic_only, phase="idle"
        )
        try:
            await asyncio.to_thread(self._audio.stop)
        except Exception:
            log.exception("audio stop failed during abort")
        await self._cancel_worker(self._worker_task)
        self._worker_task = None
        self._close_writer()
        session = await self._store.get_session(session_id)
        if session:
            await self._store.update_session(
                replace(session, ended_at=datetime.now(tz=UTC), status="stopped")
            )

    async def _cancel_worker(self, worker: asyncio.Task[None] | None) -> None:
        if not worker:
            return
        worker.cancel()
        try:
            await asyncio.wait_for(worker, timeout=1.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception as exc:
            log.warning("worker finished with error during cancel: %s", exc)

    def _enqueue(self, windows: list[tuple[list[float], int, int]], source: str) -> None:
        if not self._loop or not self.state.recording:
            return
        session_id = self.state.session_id
        if not session_id:
            return
        for samples, start_ms, end_ms in windows:
            if not samples or not has_speech(samples):
                continue
            self._loop.call_soon_threadsafe(
                self._pending.put_nowait,
                (samples, start_ms, end_ms, source, session_id),
            )

    def _enqueue_leftovers(self, session_id: str, pending: asyncio.Queue[PendingWindow]) -> None:
        for source, buf in (("mic", self._mic_buf), ("loopback", self._loop_buf)):
            leftover = buf.flush()
            if leftover and has_speech(leftover[0]):
                pending.put_nowait((leftover[0], leftover[1], leftover[2], source, session_id))

    def _on_chunk(self, chunk: AudioChunk) -> None:
        if not self.state.recording:
            return
        if self._writer:
            try:
                self._writer.write(chunk.samples)
            except Exception:
                log.exception("wav write failed session=%s", self.state.session_id)
                self._close_writer()
        mic = chunk.mic if chunk.mic is not None else chunk.samples
        loopback = None if self.state.mic_only else chunk.loopback
        self._enqueue(self._mic_buf.push(mic, chunk.timestamp_ms), "mic")
        if loopback:
            self._enqueue(self._loop_buf.push(loopback, chunk.timestamp_ms), "loopback")
        self._emit_monitor(chunk.samples)

    def _emit_monitor(self, samples: list[float]) -> None:
        if not self._loop:
            return
        now = time.monotonic()
        if now - self._last_level_emit < LEVEL_EVERY:
            return
        self._last_level_emit = now
        rms, speech, bars = chunk_monitor(samples)
        queued = self._pending.qsize()
        buffer_ms = int(
            (len(self._mic_buf.samples) + len(self._loop_buf.samples))
            * 1000
            / self._settings.sample_rate
        )
        self._bus.publish_threadsafe(
            self._loop,
            {
                "type": "monitor",
                "rms": round(rms, 4),
                "speech": speech,
                "bars": [round(item, 3) for item in bars],
                "queued": queued,
                "buffer_ms": buffer_ms,
                "phase": "transcribing" if self._transcribing else self.state.phase,
                "whisper_loaded": self.whisper_loaded(),
            },
        )

    async def _drain_after_stop(
        self,
        session_id: str,
        pending: asyncio.Queue[PendingWindow],
        worker: asyncio.Task[None] | None,
        done: asyncio.Event,
    ) -> None:
        queued = pending.qsize()
        log.info("draining leftover windows session=%s queued=%s", session_id, queued)
        if queued or self._transcribing:
            await self._bus.publish(
                {
                    "type": "asr",
                    "status": "start",
                    "queued": queued,
                    "session_id": session_id,
                    "phase": "transcribing",
                }
            )
        try:
            if worker is None or worker.done():
                worker = asyncio.create_task(self._consume_windows(pending))
            await pending.join()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("flush failed session=%s", session_id)
        finally:
            await self._cancel_worker(worker)
            await self._bus.publish(
                {
                    "type": "asr",
                    "status": "done",
                    "queued": 0,
                    "empty": False,
                    "session_id": session_id,
                    "phase": "idle",
                }
            )
            done.set()
            self._drain_events.pop(session_id, None)

    async def _consume_windows(self, pending: asyncio.Queue[PendingWindow]) -> None:
        try:
            while True:
                window, start_ms, end_ms, source, session_id = await pending.get()
                try:
                    if not window:
                        continue
                    await self._transcribe(window, start_ms, end_ms, source, session_id, pending)
                except Exception:
                    log.exception("consume window failed session=%s", session_id)
                finally:
                    pending.task_done()
        except asyncio.CancelledError:
            raise

    async def _transcribe(
        self,
        window: list[float],
        start_ms: int,
        end_ms: int,
        source: str,
        session_id: str,
        pending: asyncio.Queue[PendingWindow] | None = None,
    ) -> None:
        if not session_id:
            return
        queue = pending or self._pending
        self._transcribing = True
        await self._bus.publish(
            {
                "type": "asr",
                "status": "start",
                "queued": queue.qsize(),
                "phase": "transcribing",
                "session_id": session_id,
            }
        )
        text = ""
        language: str | None = None
        try:
            async with self._worker_lock:
                text, language = await asyncio.to_thread(
                    self._asr.transcribe_window,
                    window,
                    self._settings.sample_rate,
                    language=_locked_language(self._settings.language),
                )
                text = annotate_transcript(text, window)
        except Exception:
            log.exception("transcribe window failed session=%s", session_id)
            text, language = "", None
        finally:
            self._transcribing = False
        await self._bus.publish(
            {
                "type": "asr",
                "status": "done" if queue.qsize() == 0 else "start",
                "empty": not bool(text),
                "chars": len(text or ""),
                "queued": queue.qsize(),
                "phase": "listening" if self.state.recording else "transcribing",
                "session_id": session_id,
            }
        )
        if not text:
            log.info("whisper returned empty window session=%s", session_id)
            return
        previous = self._last_text.get(source, "")
        text = strip_overlap(previous, text)
        if not text:
            return
        self._last_text[source] = text
        speaker_id = self._speaker_for(source)
        speaker_name = next((item.name for item in self._people if item.id == speaker_id), None)
        segment = TranscriptSegment(
            id=new_id(),
            session_id=session_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            language=language,
            speaker_id=speaker_id,
            source=source,
        )
        await self._store.add_segment(segment)
        await self._bus.publish(
            {
                "type": "segment",
                "segment": {
                    "id": segment.id,
                    "session_id": segment.session_id,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text": segment.text,
                    "language": segment.language,
                    "speaker_id": segment.speaker_id,
                    "speaker_name": speaker_name,
                    "source": segment.source,
                },
            }
        )

    def _speaker_for(self, source: str) -> str | None:
        if source == "mic":
            if self._self_person_id:
                return self._self_person_id
            if len(self._people) == 1:
                return self._people[0].id
        return None


def _capture_event(state: CaptureState) -> dict[str, object]:
    return {
        "type": "capture",
        "recording": state.recording,
        "session_id": state.session_id,
        "phase": state.phase,
        "warning": state.warning,
        "loopback_name": state.loopback_name,
        "started_at": state.started_at.isoformat() if state.started_at else None,
    }


def _audio_startup_error(audio: AudioCapturePort) -> str | None:
    checker = getattr(audio, "startup_error", None)
    if callable(checker):
        message = checker()
        if message:
            return str(message)
    return None


def _default_title(mode: str = "meeting") -> str:
    now = datetime.now()
    labels = {"dictation": "Ditado", "lecture": "Aula", "meeting": "Reunião"}
    prefix = labels.get(mode, "Sessão")
    return f"{prefix} {now.strftime('%d/%m/%Y %H:%M')}"


def _normalize_mode(value: str | None) -> str:
    cleaned = (value or "meeting").strip().lower()
    if cleaned in {"dictation", "lecture", "meeting"}:
        return cleaned
    return "meeting"


def _majority_language(values: list[str | None]) -> str | None:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _locked_language(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if not cleaned or cleaned == "auto":
        return None
    return cleaned
