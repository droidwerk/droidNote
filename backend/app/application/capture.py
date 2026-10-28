from __future__ import annotations

import asyncio
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np

from app.application.bus import EventBus
from app.core.config import Settings, session_recording_path
from app.core.i18n import ui_message
from app.core.logging import get_logger
from app.domain.models import AudioChunk, Person, Session, TranscriptSegment
from app.domain.ports import AudioCapturePort, AsrPort, SessionRepository
from app.infrastructure.asr.overlap import drop_covered_words, strip_overlap
from app.infrastructure.asr.scene import annotate_transcript
from app.infrastructure.asr.vad import SpeechBuffer, chunk_monitor, has_speech, rms_level
from app.infrastructure.asr.whisper_engine import join_words
from app.infrastructure.audio.wav_writer import SessionWavWriter
from app.infrastructure.audio.windows_wasapi import WindowsWasapiCapture
from app.infrastructure.persistence.sqlite import new_id
from app.infrastructure.audio.agc import AutoGain
from app.infrastructure.voice.echo import EchoGate
from app.infrastructure.voice.vad import SileroModel, StreamingVad

if TYPE_CHECKING:
    from app.application.voices import LabeledTurn, VoiceService

log = get_logger("capture")

START_AUDIO_GRACE = 0.35
LEVEL_EVERY = 0.08
PROBE_EVERY = 0.6
PROBE_SECONDS = 1.5
PROBE_FRESH = 1.6
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
        *,
        voices: VoiceService | None = None,
        neural_vad: bool = False,
    ) -> None:
        self._settings = settings
        self._voices = voices
        self._neural_vad = neural_vad
        self._echo = EchoGate()
        self._agc = AutoGain()
        self._mic_vad = StreamingVad()
        self._loop_vad = StreamingVad()
        self._channel_level: dict[str, float] = {"mic": 0.0, "system": 0.0}
        self._channel_speech: dict[str, bool] = {"mic": False, "system": False}
        self._probe_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="droidnote-probe")
        self._probe_future: Future[None] | None = None
        self._probe_audio: dict[str, deque[np.ndarray]] = {"mic": deque(), "loopback": deque()}
        self._last_probe = 0.0
        self._now_voice: dict[str, object] | None = None
        self._now_voice_at = 0.0
        self._capture_mode = "meeting"
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
        self._covered_until: dict[str, int] = {}
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
        template_id: str | None = None,
    ) -> CaptureState:
        if self.state.recording:
            return self.state
        if not self._asr.is_ready() and not hasattr(self._asr, "load"):
            raise RuntimeError("Modelo de transcrição ainda não está pronto")

        mode = _normalize_mode(capture_mode)
        session = Session(
            id=new_id(),
            title=title or _default_title(mode, self._settings.ui_language),
            started_at=datetime.now(tz=UTC),
            ended_at=None,
            status="recording",
            language=_locked_language(self._settings.language),
            capture_mode=mode,
            template_id=template_id or None,
        )
        await self._store.create_session(session)
        self._people = []
        saved_self = await self._store.get_setting("self_person_id")
        self._self_person_id = saved_self or None
        self._last_text = {}
        self._covered_until = {}
        await self.set_participants(session.id, participant_ids or [])
        self._mic_buf = self._new_buffer()
        self._loop_buf = self._new_buffer()
        self._echo = EchoGate()
        self._agc = AutoGain(enabled=(await self._store.get_setting("auto_gain")) != "0")
        self._mic_vad = StreamingVad()
        self._loop_vad = StreamingVad()
        self._now_voice = None
        self._probe_audio = {"mic": deque(), "loopback": deque()}
        self._capture_mode = mode
        self._pending = asyncio.Queue()
        self._transcribing = False
        if self._voices is not None:
            try:
                await self._voices.begin(
                    session.id,
                    mode=mode,
                    self_person_id=self._self_person_id,
                    call=not mic_only,
                )
            except Exception:
                log.exception("voice engine start failed session=%s", session.id)
        if self._neural_vad:
            await asyncio.to_thread(SileroModel.get)
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
        if self._voices is not None and self.state.session_id:
            self._voices.set_self(self.state.session_id, self._self_person_id)

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
            if not samples:
                continue
            if not self._neural_vad and not has_speech(samples):
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
        if loopback:
            # Sem fone, o microfone escuta o alto-falante: o eco sai do canal do
            # microfone antes da transcrição (o WAV continua com tudo).
            mic = self._echo.process(np.asarray(mic, dtype=np.float32), np.asarray(loopback, dtype=np.float32)).tolist()
        if self._agc.enabled:
            mic = self._agc.process(np.asarray(mic, dtype=np.float32)).tolist()
        mic_mask = self._mic_vad.mask(mic) if self._neural_vad else None
        self._channel_level["mic"] = rms_level(mic)
        self._channel_speech["mic"] = bool(mic_mask.any()) if mic_mask is not None else has_speech(mic)
        self._enqueue(self._mic_buf.push(mic, chunk.timestamp_ms, mic_mask), "mic")
        if loopback:
            loop_mask = self._loop_vad.mask(loopback) if self._neural_vad else None
            self._channel_level["system"] = rms_level(loopback)
            self._channel_speech["system"] = (
                bool(loop_mask.any()) if loop_mask is not None else has_speech(loopback)
            )
            self._enqueue(self._loop_buf.push(loopback, chunk.timestamp_ms, loop_mask), "loopback")
        else:
            self._channel_level["system"] = 0.0
            self._channel_speech["system"] = False
        self._feed_probe("mic", mic)
        if loopback:
            self._feed_probe("loopback", loopback)
        self._maybe_probe()
        self._emit_monitor(chunk.samples)

    def _feed_probe(self, source: str, samples: list[float]) -> None:
        if self._voices is None:
            return
        buf = self._probe_audio[source]
        buf.append(np.asarray(samples, dtype=np.float32))
        limit = int(PROBE_SECONDS * self._settings.sample_rate)
        while sum(item.size for item in buf) - buf[0].size >= limit:
            buf.popleft()

    def _maybe_probe(self) -> None:
        """A cada ~0,6 s, compara o último 1,5 s do canal com voz às vozes da sessão."""
        voices = self._voices
        session_id = self.state.session_id
        if voices is None or not session_id or not voices.is_live(session_id):
            return
        now = time.monotonic()
        if now - self._last_probe < PROBE_EVERY:
            return
        if self._probe_future is not None and not self._probe_future.done():
            return
        speaking = [
            (self._channel_level["system" if source == "loopback" else "mic"], source)
            for source in ("mic", "loopback")
            if self._channel_speech["system" if source == "loopback" else "mic"]
        ]
        if not speaking:
            return
        _, source = max(speaking)
        clip = np.concatenate(list(self._probe_audio[source])) if self._probe_audio[source] else None
        if clip is None or clip.size < int(self._settings.sample_rate):
            return
        self._last_probe = now

        def run() -> None:
            try:
                found = voices.probe(session_id, clip)
            except Exception:
                log.exception("voice probe failed")
                return
            if found is None:
                return
            cluster, person_id, score = found
            name = next((item.name for item in self._people if item.id == person_id), None)
            self._now_voice = {
                "cluster": cluster,
                "person_id": person_id,
                "name": name,
                "source": source,
                "at_ms": 0,
                "similarity": round(score, 3),
            }
            self._now_voice_at = time.monotonic()

        self._probe_future = self._probe_pool.submit(run)

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
                "channels": {
                    "mic": {
                        "rms": round(self._channel_level["mic"], 4),
                        "speech": self._channel_speech["mic"],
                        "echo": round(self._echo.gated_ratio, 3),
                        "gain_db": round(self._agc.gain_db, 1),
                    },
                    "system": None
                    if self.state.mic_only
                    else {
                        "rms": round(self._channel_level["system"], 4),
                        "speech": self._channel_speech["system"],
                    },
                },
                "voice": self._now_voice
                if self._now_voice is not None and now - self._now_voice_at < PROBE_FRESH
                else None,
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
        await self._mark_asr(True, session_id, queue)
        words: list[tuple[float, float, str]] = []
        language: str | None = None
        turns: list[LabeledTurn] | None = None
        overlap_only = False
        try:
            async with self._worker_lock:
                words, language = await asyncio.to_thread(self._words_for, window)
                covered = self._covered_until.get(source)
                fresh = drop_covered_words(words, start_ms, covered)
                self._covered_until[source] = end_ms if covered is None else max(covered, end_ms)
                overlap_only = bool(words) and not fresh
                words = fresh
                if not overlap_only:
                    turns = await self._label(session_id, source, window, start_ms, words)
        except Exception:
            log.exception("transcribe window failed session=%s", session_id)
            words, language, turns = [], None, None
            overlap_only = False
        finally:
            await self._mark_asr(False, session_id, queue)
        if overlap_only:
            return
        if not turns:
            text = annotate_transcript(join_words(words), window)
            if not text:
                log.info("whisper returned empty window session=%s", session_id)
                return
            turns = None
            pieces: list[tuple[int, int, str, str | None, str | None, float | None]] = [
                (start_ms, end_ms, text, None, self._speaker_for(source), None)
            ]
        else:
            pieces = [
                (item.start_ms, item.end_ms, item.text, item.cluster, item.person_id, item.confidence)
                for item in turns
            ]
        previous = self._last_text.get(source, "")
        first_start, first_end, first_text, *rest = pieces[0]
        trimmed = strip_overlap(previous, first_text)
        pieces[0] = (first_start, first_end, trimmed, *rest)  # type: ignore[assignment]
        emitted = 0
        for index, (seg_start, seg_end, text, cluster, person_id, confidence) in enumerate(pieces):
            if not text:
                continue
            if person_id is None and cluster is None:
                person_id = self._speaker_for(source)
            segment = TranscriptSegment(
                id=new_id(),
                session_id=session_id,
                start_ms=seg_start,
                end_ms=max(seg_end, seg_start + 1),
                text=text,
                language=language,
                speaker_id=person_id,
                source=source,
                speaker_cluster=cluster,
                speaker_confidence=confidence,
            )
            await self._store.add_segment(segment)
            if turns is not None and self._voices is not None:
                try:
                    await self._voices.persist_turn(segment, turns[index])
                except Exception:
                    log.exception("voice persist failed segment=%s", segment.id)
            self._last_text[source] = text
            emitted += 1
            await self._publish_segment(segment)
        if emitted and turns is not None and self._voices is not None:
            self._voices.schedule_refine(session_id)

    def _words_for(self, window: list[float]) -> tuple[list[tuple[float, float, str]], str | None]:
        language = _locked_language(self._settings.language)
        transcriber = getattr(self._asr, "transcribe_words", None)
        if callable(transcriber):
            words, detected = transcriber(window, self._settings.sample_rate, language=language)
            return list(words), detected
        text, detected = self._asr.transcribe_window(
            window, self._settings.sample_rate, language=language
        )
        if not text:
            return [], detected
        return [(0.0, len(window) / float(self._settings.sample_rate), text)], detected

    async def _label(
        self,
        session_id: str,
        source: str,
        window: list[float],
        start_ms: int,
        words: list[tuple[float, float, str]],
    ) -> list[LabeledTurn] | None:
        voices = self._voices
        if voices is None or not words or not voices.is_live(session_id):
            return None
        audio = np.asarray(window, dtype=np.float32)
        speech = None
        if self._neural_vad:
            probs = await asyncio.to_thread(SileroModel.probabilities, audio)
            if probs is not None:
                speech = np.repeat(probs >= 0.5, 512)[: audio.size]
        try:
            return await asyncio.to_thread(
                voices.label_window, session_id, source, audio, start_ms, words, speech
            )
        except Exception:
            log.exception("voice labeling failed session=%s", session_id)
            return None

    async def _publish_segment(self, segment: TranscriptSegment) -> None:
        speaker_name = next(
            (item.name for item in self._people if item.id == segment.speaker_id), None
        )
        if speaker_name is None and segment.speaker_id:
            person = await self._store.get_person(segment.speaker_id)
            speaker_name = person.name if person else None
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
                    "speaker_cluster": segment.speaker_cluster,
                    "speaker_confidence": segment.speaker_confidence,
                    "speaker_locked": False,
                },
            }
        )

    async def _mark_asr(
        self,
        busy: bool,
        session_id: str,
        queue: asyncio.Queue[PendingWindow],
    ) -> None:
        queued = queue.qsize()
        if busy:
            if self._transcribing:
                return
            self._transcribing = True
            await self._bus.publish(
                {
                    "type": "asr",
                    "status": "start",
                    "queued": queued,
                    "phase": "transcribing",
                    "session_id": session_id,
                }
            )
            return
        if queued > 0:
            return
        if not self._transcribing:
            return
        self._transcribing = False
        await self._bus.publish(
            {
                "type": "asr",
                "status": "done",
                "empty": False,
                "queued": 0,
                "phase": "listening" if self.state.recording else "idle",
                "session_id": session_id,
            }
        )

    def _speaker_for(self, source: str) -> str | None:
        if source == "mic" and self._capture_mode == "lecture":
            # Em aula o microfone pega quem ensina, não quem grava.
            return self._people[0].id if len(self._people) == 1 else None
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


def _default_title(mode: str = "meeting", locale: str | None = None) -> str:
    now = datetime.now()
    keys = {
        "dictation": "title_dictation",
        "lecture": "title_lecture",
        "meeting": "title_meeting",
    }
    prefix = ui_message(locale, keys.get(mode, "title_session"))
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
