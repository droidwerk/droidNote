"""Motor de voz da sessão: quem falou, com memória entre gravações.

Ao vivo, cada janela de áudio é diarizada (`diarize_window`) e cada turno sai
com uma voz ("v1", "v2"…). A cada ~40 s de fala nova, a sessão inteira é
reagrupada com clusterização espectral, que corrige a fragmentação típica do
modo incremental — os rótulos na tela se ajustam sozinhos. No fim da gravação,
o mesmo reagrupamento roda uma última vez.

Quando o usuário dá nome a uma voz, todos os trechos daquela voz recebem o
nome e a impressão vocal da pessoa é atualizada. Na próxima gravação, ela é
reconhecida sem ninguém precisar rotular de novo.
"""

from __future__ import annotations

import asyncio
import threading
import wave
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from app.application.bus import EventBus
from app.core.logging import get_logger
from app.domain.models import SessionVoice, TranscriptSegment
from app.infrastructure.voice.diarize import Turn, Word, diarize_window, window_embeddings
from app.infrastructure.voice.embedder import normalize
from app.infrastructure.voice.tracker import (
    KNOWN_THRESHOLD,
    MERGE_THRESHOLD,
    SpeakerTracker,
    VoiceCluster,
    blend_voiceprint,
    spectral_labels,
)

log = get_logger("voices")

REFINE_EVERY_S = 40.0
# No começo da reunião os rótulos ao vivo erram mais (pouca fala por voz): os
# primeiros reagrupamentos vêm cedo e vão espaçando até o ritmo normal.
REFINE_EARLY_S = (10.0, 15.0, 20.0, 30.0)
REFINE_AFTER_NEW_VOICE_S = 15.0
MAX_REFINE_FRAMES = 1200
# Duas vozes com pessoas diferentes nunca se fundem: um grupo em que cada uma
# tem pelo menos isto de fala, e cujas impressões são mesmo distintas, é
# separado de novo.
NAMED_SHARE_MIN_S = 5.0
SELF_ENROLL_MIN_S = 20.0
PROBE_THRESHOLD = 0.45
# "Falando agora" por impressão vocal guardada: 1,5 s de áudio contra as pessoas
# conhecidas. Precisa de duas sondas seguidas concordando para mostrar o nome.
PROBE_KNOWN_THRESHOLD = 0.5
PROBE_KNOWN_HITS = 2


class VoiceEmbedderPort(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def is_ready(self) -> bool: ...

    def embed(self, samples: Sequence[float] | np.ndarray, sample_rate: int = 16_000) -> np.ndarray | None: ...

    def embed_batch(self, features: np.ndarray) -> np.ndarray | None: ...


@dataclass(frozen=True)
class LabeledTurn:
    start_ms: int
    end_ms: int
    text: str
    cluster: str | None
    person_id: str | None
    confidence: float
    embedding: np.ndarray | None
    frames: np.ndarray | None


@dataclass
class LiveVoices:
    session_id: str
    mode: str
    self_person_id: str | None
    call: bool
    tracker: SpeakerTracker
    lock: threading.Lock = field(default_factory=threading.Lock)
    speech_since_refine: float = 0.0
    total_speech: float = 0.0
    new_voice: bool = False
    revision: int = 0
    refining: bool = False
    refines: int = 0
    self_linked: bool = False
    probe_person: str | None = None
    probe_hits: int = 0
    # Número de vozes já aceito pelo reagrupamento e o candidato que precisa
    # se repetir na rodada seguinte para ser aceito.
    accepted_count: int | None = None
    candidate_count: int | None = None


class VoiceService:
    def __init__(
        self,
        embedder: VoiceEmbedderPort | None,
        store: object,
        bus: EventBus,
        recordings_path: object | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._bus = bus
        self._recordings_path = recordings_path
        self._live: dict[str, LiveVoices] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # --- estado -----------------------------------------------------------

    @property
    def embedder(self) -> VoiceEmbedderPort | None:
        return self._embedder

    def available(self) -> bool:
        return self._embedder is not None and self._embedder.is_ready()

    def model_id(self) -> str:
        return self._embedder.model_id if self._embedder is not None else ""

    def is_live(self, session_id: str) -> bool:
        return session_id in self._live

    async def begin(
        self,
        session_id: str,
        *,
        mode: str,
        self_person_id: str | None,
        call: bool,
    ) -> bool:
        if not self.available():
            return False
        known = await self._known_voiceprints()
        self._live[session_id] = LiveVoices(
            session_id=session_id,
            mode=mode,
            self_person_id=self_person_id or None,
            call=call,
            tracker=SpeakerTracker(known),
        )
        log.info("voices live session=%s known=%s mode=%s call=%s", session_id, len(known), mode, call)
        return True

    def set_self(self, session_id: str, person_id: str | None) -> None:
        live = self._live.get(session_id)
        if live is not None:
            live.self_person_id = person_id or None

    def set_call(self, session_id: str, call: bool) -> None:
        live = self._live.get(session_id)
        if live is not None:
            live.call = call

    async def finish(self, session_id: str) -> None:
        """Fim da gravação: reagrupamento final e memória da voz de quem gravou."""
        live = self._live.get(session_id)
        try:
            await self.refine(session_id, final=True)
            if live is not None:
                await self._enroll_self(live)
        except Exception:
            log.exception("final voice refine failed session=%s", session_id)
        finally:
            self._live.pop(session_id, None)

    # --- ao vivo ------------------------------------------------------------

    def label_window(
        self,
        session_id: str,
        source: str,
        samples: Sequence[float] | np.ndarray,
        start_ms: int,
        words: Sequence[tuple[float, float, str]],
        speech: np.ndarray | None = None,
    ) -> list[LabeledTurn] | None:
        """Roda numa thread (CPU). None = motor de voz fora; quem chama usa o canal."""
        live = self._live.get(session_id)
        embedder = self._embedder
        if live is None or embedder is None or not words:
            return None
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        with live.lock:
            before = len(live.tracker.clusters)
            turns = diarize_window(
                embedder,
                live.tracker,
                audio,
                [Word(*item) for item in words],
                source=source,
                offset_ms=start_ms,
                speech=speech,
            )
            if len(live.tracker.clusters) > before:
                live.new_voice = True
            labeled = [self._resolve_live(live, turn, source, start_ms) for turn in turns]
        spoken = sum(max(0, item.end_ms - item.start_ms) for item in labeled) / 1000.0
        live.speech_since_refine += spoken
        live.total_speech += spoken
        return labeled

    def probe(self, session_id: str, samples: np.ndarray) -> tuple[str | None, str | None, float] | None:
        """Quem está falando agora: compara 1,5 s de áudio com as vozes da sessão
        e com as impressões vocais guardadas, sem criar voz nova. Uma pessoa
        conhecida aparece pelo nome antes mesmo de a transcrição chegar.
        Roda fora da thread de áudio."""
        live = self._live.get(session_id)
        embedder = self._embedder
        if live is None or embedder is None:
            return None
        vector = embedder.embed(samples)
        if vector is None:
            return None
        if not live.lock.acquire(blocking=False):
            return None
        try:
            vector = normalize(vector)
            cluster, score = live.tracker.best_cluster(vector)
            person_id, person_score = live.tracker.best_person(vector)
            known = self._confirm_known(live, person_id, person_score)
            if cluster is not None and score >= PROBE_THRESHOLD:
                return cluster.key, cluster.person_id or known, score
            if known:
                return None, known, person_score
            return None
        finally:
            live.lock.release()

    @staticmethod
    def _confirm_known(live: LiveVoices, person_id: str | None, score: float) -> str | None:
        if not person_id or score < PROBE_KNOWN_THRESHOLD:
            live.probe_person, live.probe_hits = None, 0
            return None
        if live.probe_person == person_id:
            live.probe_hits += 1
        else:
            live.probe_person, live.probe_hits = person_id, 1
        return person_id if live.probe_hits >= PROBE_KNOWN_HITS else None

    def _resolve_live(self, live: LiveVoices, turn: Turn, source: str, start_ms: int) -> LabeledTurn:
        person = turn.person_id
        cluster = live.tracker.clusters.get(turn.cluster or "")
        if person is None and cluster is not None and source == "mic" and self._self_applies(live):
            if live.mode == "dictation" or not live.self_linked:
                cluster.person_id = live.self_person_id
                live.self_linked = True
                person = live.self_person_id
        return LabeledTurn(
            start_ms=start_ms + int(turn.start * 1000),
            end_ms=start_ms + int(max(turn.end, turn.start + 0.2) * 1000),
            text=turn.text,
            cluster=turn.cluster,
            person_id=person,
            confidence=round(max(0.0, min(1.0, turn.similarity)), 3),
            embedding=turn.embedding,
            frames=turn.frames,
        )

    @staticmethod
    def _self_applies(live: LiveVoices) -> bool:
        if not live.self_person_id:
            return False
        return live.mode == "dictation" or (live.mode == "meeting" and live.call)

    async def persist_turn(self, segment: TranscriptSegment, turn: LabeledTurn) -> None:
        if turn.embedding is None:
            return
        frames = turn.frames if turn.frames is not None else turn.embedding[None, :]
        await self._store.save_segment_voice(  # type: ignore[attr-defined]
            segment.id,
            segment.session_id,
            dim=int(turn.embedding.size),
            embedding=normalize(turn.embedding).astype(np.float32).tobytes(),
            frames=np.asarray(frames, dtype=np.float16).tobytes(),
            frame_count=int(frames.shape[0]),
        )

    def schedule_refine(self, session_id: str) -> None:
        live = self._live.get(session_id)
        if live is None or live.refining:
            return
        every = REFINE_EARLY_S[live.refines] if live.refines < len(REFINE_EARLY_S) else REFINE_EVERY_S
        due = live.speech_since_refine >= every or (
            live.new_voice and live.speech_since_refine >= REFINE_AFTER_NEW_VOICE_S
        )
        if not due:
            return
        live.refining = True
        task = asyncio.create_task(self._refine_live(session_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _refine_live(self, session_id: str) -> None:
        live = self._live.get(session_id)
        try:
            await self.refine(session_id)
        except Exception:
            log.exception("live voice refine failed session=%s", session_id)
        finally:
            if live is not None:
                live.refining = False
                live.refines += 1
                live.new_voice = False
                live.speech_since_refine = 0.0

    # --- reagrupamento ------------------------------------------------------

    async def refine(self, session_id: str, *, final: bool = False) -> list[TranscriptSegment]:
        """Reagrupa as vozes da sessão inteira e corrige os rótulos."""
        segments = await self._store.list_segments(session_id)  # type: ignore[attr-defined]
        if not segments:
            return segments
        frames_by_segment = await self._load_frames(session_id)
        if not frames_by_segment and final:
            frames_by_segment = await self._backfill_from_wav(session_id, segments)
        if not frames_by_segment:
            return segments
        by_id = {item.id: item for item in segments}
        order = [item.id for item in segments if item.id in frames_by_segment]
        units, owners = _units(order, frames_by_segment)
        if len(units) == 0:
            return segments
        links = await self._store.list_session_voices(session_id)  # type: ignore[attr-defined]
        live = self._live.get(session_id)
        labels = await asyncio.to_thread(spectral_labels, units)
        labels = await self._settle_count(live, units, labels, final)
        labels = _split_named(units, owners, labels, by_id, links)

        votes: dict[str, Counter[int]] = defaultdict(Counter)
        for owner, label in zip(owners, labels):
            votes[owner][label] += 1
        group_of = {segment_id: counter.most_common(1)[0][0] for segment_id, counter in votes.items()}

        # Rótulos estáveis: cada grupo novo herda a voz antiga com mais tempo em comum.
        overlap: dict[int, Counter[str]] = defaultdict(Counter)
        duration: dict[int, float] = defaultdict(float)
        for segment_id, group in group_of.items():
            segment = by_id[segment_id]
            spoken = max(1, segment.end_ms - segment.start_ms)
            duration[group] += spoken
            if segment.speaker_cluster:
                overlap[group][segment.speaker_cluster] += spoken
        key_of: dict[int, str] = {}
        taken: set[str] = set()
        for group in sorted(duration, key=lambda item: -duration[item]):
            for key, _ in overlap[group].most_common():
                if key not in taken:
                    key_of[group] = key
                    taken.add(key)
                    break
        used_numbers = {int(k[1:]) for k in taken if k[1:].isdigit()}
        next_number = 1
        for group in sorted(duration, key=lambda item: min(by_id[s].start_ms for s, g in group_of.items() if g == item)):
            if group in key_of:
                continue
            while next_number in used_numbers:
                next_number += 1
            key_of[group] = f"v{next_number}"
            used_numbers.add(next_number)

        # Cada grupo herda a pessoa da voz antiga com mais tempo entre os seus
        # trechos, e não só da voz cuja chave ele herdou: quando uma voz com nome
        # é absorvida por outra sem nome, o nome fica com o grupo.
        group_links = _inherit_links(group_of, by_id, links)
        if key_of:
            # Numeração compacta pela ordem em que cada voz apareceu: quem falou
            # primeiro mantém o número; só vozes novas ou fundidas se reorganizam.
            first_at = {
                group: min(by_id[s].start_ms for s, g in group_of.items() if g == group)
                for group in key_of
            }
            renamed = {group: f"v{index}" for index, group in enumerate(sorted(key_of, key=first_at.get), start=1)}
            links = {renamed[g]: group_links[g] for g in key_of if group_links.get(g)}
            key_of = renamed
        known = await self._known_voiceprints()
        centroids: dict[str, np.ndarray] = {}
        for group, key in key_of.items():
            members = [i for i, owner in enumerate(owners) if group_of.get(owner) == group]
            if members:
                centroids[key] = normalize(units[members].sum(axis=0))
        chosen_link = _unique_links(key_of, links, known, centroids, _talk_seconds(key_of, group_of, by_id))
        person_of = self._resolve_people(
            key_of, group_of, by_id, chosen_link, known, centroids, live
        )

        rows: list[tuple[str, str | None, float | None, str | None]] = []
        for segment_id, group in group_of.items():
            key = key_of[group]
            centroid = centroids.get(key)
            frames = frames_by_segment[segment_id]
            confidence = (
                float(np.clip(np.mean(frames @ centroid), 0.0, 1.0)) if centroid is not None else None
            )
            rows.append((segment_id, key, round(confidence, 3) if confidence is not None else None, person_of.get(key)))
        await self._store.update_segment_voices(rows)  # type: ignore[attr-defined]
        # Só os nomes dados pelo usuário ficam gravados como vínculo da voz. Os
        # reconhecidos pela impressão vocal são refeitos a cada rodada a partir
        # dos centróides: gravá-los fazia um acerto frágil virar permanente.
        await self._store.replace_session_voices(session_id, dict(chosen_link))  # type: ignore[attr-defined]

        if live is not None:
            with live.lock:
                rebuilt = SpeakerTracker(known)
                for key, centroid in centroids.items():
                    seconds = sum(
                        (by_id[s].end_ms - by_id[s].start_ms) / 1000.0
                        for s, g in group_of.items()
                        if key_of[g] == key
                    )
                    index = int(key[1:]) if key[1:].isdigit() else len(rebuilt.clusters) + 1
                    rebuilt.clusters[key] = VoiceCluster(
                        key=key,
                        index=index,
                        total=centroid * max(seconds, 1.0),
                        seconds=seconds,
                        person_id=person_of.get(key),
                    )
                    rebuilt._next = max(rebuilt._next, index + 1)
                rebuilt.pending = live.tracker.pending
                live.tracker = rebuilt
                live.self_linked = any(
                    person and person == live.self_person_id for person in person_of.values()
                )
                live.revision += 1
        await self._bus.publish(
            {
                "type": "voices",
                "session_id": session_id,
                "revision": live.revision if live else 0,
                "final": final,
                "count": len(key_of),
            }
        )
        log.info("voices refined session=%s voices=%s segments=%s final=%s", session_id, len(key_of), len(rows), final)
        return await self._store.list_segments(session_id)  # type: ignore[attr-defined]

    @staticmethod
    async def _settle_count(
        live: LiveVoices | None,
        units: np.ndarray,
        labels: list[int],
        final: bool,
    ) -> list[int]:
        """Histerese no número de vozes: a estimativa do eigengap oscila de uma
        rodada para outra (3, 5, 3, 5...) e cada oscilação funde ou separa vozes
        na tela. Um número diferente do aceito só entra se vier em duas rodadas
        seguidas; até lá, a sessão é reagrupada com o número já aceito."""
        proposed = len(set(labels))
        if live is None:
            return labels
        accepted = live.accepted_count
        # No começo há pouca fala por voz e as vozes ainda estão chegando: as
        # rodadas iniciais entram sem segurar. Uma voz só também não segura
        # nada: qualquer separação proposta vale mais do que ela.
        settling = live.refines < len(REFINE_EARLY_S) or accepted == 1
        if accepted is None or proposed == accepted or settling:
            live.accepted_count = proposed
            live.candidate_count = None
            return labels
        if proposed == live.candidate_count:
            live.accepted_count = proposed
            live.candidate_count = None
            return labels
        live.candidate_count = None if final else proposed
        log.info("voices count held at %s (proposed %s)", accepted, proposed)
        return await asyncio.to_thread(spectral_labels, units, None, speakers=accepted)

    def _resolve_people(
        self,
        key_of: dict[int, str],
        group_of: dict[str, int],
        by_id: dict[str, TranscriptSegment],
        links: dict[str, str | None],
        known: dict[str, np.ndarray],
        centroids: dict[str, np.ndarray],
        live: LiveVoices | None,
    ) -> dict[str, str | None]:
        person_of: dict[str, str | None] = {}
        mic_seconds: dict[str, float] = defaultdict(float)
        for segment_id, group in group_of.items():
            key = key_of[group]
            segment = by_id[segment_id]
            if segment.source == "mic":
                mic_seconds[key] += (segment.end_ms - segment.start_ms) / 1000.0
        for group, key in key_of.items():
            # 1) nome dado pelo usuário a esta voz (já único por pessoa)
            if links.get(key):
                person_of[key] = links[key]
                continue
            # 2) trechos rotulados à mão dentro do grupo
            locked = Counter(
                by_id[s].speaker_id
                for s, g in group_of.items()
                if g == group and by_id[s].speaker_locked and by_id[s].speaker_id
            )
            if locked:
                person_of[key] = locked.most_common(1)[0][0]
                continue
            # 3) impressão vocal salva
            centroid = centroids.get(key)
            best, score = None, -1.0
            if centroid is not None:
                for person_id, print_ in known.items():
                    if print_.size != centroid.size:
                        continue
                    value = float(np.dot(print_, centroid))
                    if value > score:
                        best, score = person_id, value
            if best and score >= KNOWN_THRESHOLD and best not in person_of.values():
                person_of[key] = best
                continue
            person_of[key] = None
        # 4) quem grava: a voz com mais tempo no microfone, em ditado ou chamada
        if live is not None and self._self_applies(live) and live.self_person_id:
            if live.self_person_id not in person_of.values() and mic_seconds:
                if live.mode == "dictation":
                    for key in mic_seconds:
                        if person_of.get(key) is None:
                            person_of[key] = live.self_person_id
                else:
                    top = max(mic_seconds, key=mic_seconds.get)
                    if person_of.get(top) is None:
                        person_of[top] = live.self_person_id
        return person_of

    async def _load_frames(self, session_id: str) -> dict[str, np.ndarray]:
        rows = await self._store.list_segment_voices(session_id)  # type: ignore[attr-defined]
        frames: dict[str, np.ndarray] = {}
        for segment_id, dim, _embedding, blob, count in rows:
            if not blob or dim <= 0:
                continue
            data = np.frombuffer(blob, dtype=np.float16).astype(np.float32)
            if data.size != dim * max(count, 1):
                continue
            frames[segment_id] = data.reshape(-1, dim)
        return frames

    async def _backfill_from_wav(
        self, session_id: str, segments: list[TranscriptSegment]
    ) -> dict[str, np.ndarray]:
        """Sessão antiga, sem vozes: tira as impressões do WAV gravado."""
        embedder = self._embedder
        resolver = self._recordings_path
        if embedder is None or not callable(resolver) or not self.available():
            return {}
        path = resolver(session_id)
        if not isinstance(path, Path) or not path.is_file():
            return {}
        audio = await asyncio.to_thread(_read_wav, path)
        if audio is None:
            return {}
        frames: dict[str, np.ndarray] = {}

        def compute() -> None:
            for segment in segments:
                lo = max(0, segment.start_ms * 16)
                hi = min(audio.size, segment.end_ms * 16)
                if hi - lo < 16_000:
                    continue
                cores = window_embeddings(embedder, audio[lo:hi])
                if not cores:
                    continue
                frames[segment.id] = np.stack([core.embedding for core in cores])

        await asyncio.to_thread(compute)
        for segment_id, stack in frames.items():
            await self._store.save_segment_voice(  # type: ignore[attr-defined]
                segment_id,
                session_id,
                dim=int(stack.shape[1]),
                embedding=normalize(stack.sum(axis=0)).astype(np.float32).tobytes(),
                frames=stack.astype(np.float16).tobytes(),
                frame_count=int(stack.shape[0]),
            )
        log.info("voices backfilled from wav session=%s segments=%s", session_id, len(frames))
        return frames

    # --- nomes e memória ------------------------------------------------------

    async def assign(self, session_id: str, cluster: str, person_id: str | None) -> None:
        await self._store.assign_cluster_person(session_id, cluster, person_id)  # type: ignore[attr-defined]
        live = self._live.get(session_id)
        if live is not None:
            with live.lock:
                live.tracker.link(cluster, person_id)
                if person_id and person_id == live.self_person_id:
                    live.self_linked = True
        if person_id:
            await self.enroll_cluster(session_id, cluster, person_id)
        await self._bus.publish(
            {"type": "voices", "session_id": session_id, "revision": live.revision if live else 0, "final": False}
        )

    async def enroll_cluster(self, session_id: str, cluster: str, person_id: str) -> None:
        if self._embedder is None:
            return
        segments = await self._store.list_segments(session_id)  # type: ignore[attr-defined]
        members = {item.id: item for item in segments if item.speaker_cluster == cluster}
        if not members:
            return
        frames = await self._load_frames(session_id)
        additions = [
            (normalize(frames[segment_id].sum(axis=0)), (members[segment_id].end_ms - members[segment_id].start_ms) / 1000.0)
            for segment_id in members
            if segment_id in frames and _reliable(members[segment_id])
        ]
        await self._enroll(person_id, additions)

    async def _enroll(self, person_id: str, additions: list[tuple[np.ndarray, float]]) -> None:
        if not additions or self._embedder is None:
            return
        model = self._embedder.model_id
        stored = await self._store.list_voiceprints(model)  # type: ignore[attr-defined]
        current = None
        samples = 0
        if person_id in stored:
            dim, blob, samples = stored[person_id]
            current = np.frombuffer(blob, dtype=np.float32)
            if current.size != dim:
                current, samples = None, 0
        vector, count = blend_voiceprint(current, samples, additions)
        await self._store.save_voiceprint(  # type: ignore[attr-defined]
            person_id, model=model, dim=int(vector.size), embedding=vector.astype(np.float32).tobytes(), samples=count
        )
        log.info("voiceprint updated person=%s samples=%s", person_id, count)

    async def _enroll_self(self, live: LiveVoices) -> None:
        if not live.self_person_id or not self._self_applies(live) or live.total_speech < SELF_ENROLL_MIN_S:
            return
        segments = await self._store.list_segments(live.session_id)  # type: ignore[attr-defined]
        clusters = {item.speaker_cluster for item in segments if item.speaker_id == live.self_person_id and item.speaker_cluster}
        for cluster in clusters:
            await self.enroll_cluster(live.session_id, cluster, live.self_person_id)

    async def forget(self, person_id: str) -> None:
        await self._store.delete_voiceprint(person_id)  # type: ignore[attr-defined]

    async def _known_voiceprints(self) -> dict[str, np.ndarray]:
        if self._embedder is None:
            return {}
        stored = await self._store.list_voiceprints(self._embedder.model_id)  # type: ignore[attr-defined]
        out: dict[str, np.ndarray] = {}
        for person_id, (dim, blob, _samples) in stored.items():
            vector = np.frombuffer(blob, dtype=np.float32)
            if vector.size == dim:
                out[person_id] = normalize(vector)
        return out

    # --- leitura ---------------------------------------------------------------

    async def voices(self, session_id: str) -> list[SessionVoice]:
        segments = await self._store.list_segments(session_id)  # type: ignore[attr-defined]
        return summarize_voices(segments)


def summarize_voices(segments: Sequence[TranscriptSegment]) -> list[SessionVoice]:
    talk: dict[str, int] = defaultdict(int)
    count: Counter[str] = Counter()
    first: dict[str, int] = {}
    sources: dict[str, Counter[str]] = defaultdict(Counter)
    people: dict[str, Counter[str]] = defaultdict(Counter)
    confidence: dict[str, list[float]] = defaultdict(list)
    for item in segments:
        key = item.speaker_cluster
        if not key:
            continue
        talk[key] += max(0, item.end_ms - item.start_ms)
        count[key] += 1
        first[key] = min(first.get(key, item.start_ms), item.start_ms)
        if item.source:
            sources[key][item.source] += 1
        if item.speaker_id:
            people[key][item.speaker_id] += 1
        if item.speaker_confidence is not None:
            confidence[key].append(item.speaker_confidence)
    voices = [
        SessionVoice(
            cluster=key,
            index=int(key[1:]) if key[1:].isdigit() else 0,
            person_id=people[key].most_common(1)[0][0] if people[key] else None,
            talk_ms=talk[key],
            segments=count[key],
            first_ms=first.get(key, 0),
            sources=tuple(source for source, _ in sources[key].most_common()),
            confidence=round(float(np.mean(confidence[key])), 3) if confidence[key] else 0.0,
        )
        for key in talk
    ]
    return sorted(voices, key=lambda item: item.first_ms)


ENROLL_MIN_CONFIDENCE = 0.5
ENROLL_MIN_MS = 1_000


def _reliable(segment: TranscriptSegment) -> bool:
    """Trecho que entra na impressão vocal: fala de verdade e bem parecida com a
    voz. Trechos de 0,5 s ou com confiança baixa sujavam a impressão, e uma
    impressão suja rotulava a pessoa errada nas reuniões seguintes."""
    if segment.end_ms - segment.start_ms < ENROLL_MIN_MS:
        return False
    return segment.speaker_confidence is None or segment.speaker_confidence >= ENROLL_MIN_CONFIDENCE


def _talk_seconds(
    key_of: dict[int, str], group_of: dict[str, int], by_id: dict[str, TranscriptSegment]
) -> dict[str, float]:
    seconds: dict[str, float] = defaultdict(float)
    for segment_id, group in group_of.items():
        segment = by_id[segment_id]
        seconds[key_of[group]] += (segment.end_ms - segment.start_ms) / 1000.0
    return seconds


def _unique_links(
    key_of: dict[int, str],
    links: dict[str, str | None],
    known: dict[str, np.ndarray],
    centroids: dict[str, np.ndarray],
    seconds: dict[str, float],
) -> dict[str, str]:
    """Uma pessoa só pode ser uma voz. Se dois vínculos apontam a mesma pessoa
    (sessão antiga, ou nome dado a duas vozes), fica com a voz cujo centróide
    mais parece com a impressão guardada; sem impressão, a que mais falou."""
    by_person: dict[str, list[str]] = defaultdict(list)
    for key in key_of.values():
        person = links.get(key)
        if person:
            by_person[person].append(key)
    chosen: dict[str, str] = {}
    for person, keys in by_person.items():
        print_ = known.get(person)

        def score(key: str) -> float:
            centroid = centroids.get(key)
            if print_ is not None and centroid is not None and print_.size == centroid.size:
                return float(np.dot(print_, centroid)) + 1.0
            return seconds.get(key, 0.0) / 1e6

        chosen[max(keys, key=score)] = person
    return chosen


def _split_named(
    units: np.ndarray,
    owners: list[str],
    labels: list[int],
    by_id: dict[str, TranscriptSegment],
    links: dict[str, str | None],
) -> list[int]:
    """Um grupo novo que junta duas vozes com pessoas diferentes é separado de
    novo: cada unidade vai para a pessoa de centróide mais próximo.

    Só vale quando as impressões das pessoas são distintas de fato (centróides
    abaixo do limiar de fusão). Pessoas "diferentes" com a mesma impressão são
    um erro de rótulo ao vivo, não duas vozes, e aí o grupo fica inteiro."""
    if not links or not labels:
        return labels
    person_of_unit = [links.get(by_id[owner].speaker_cluster or "") for owner in owners]
    units_per_segment = Counter(owners)
    seconds_of = {
        segment_id: max(0.0, (by_id[segment_id].end_ms - by_id[segment_id].start_ms) / 1000.0) / count
        for segment_id, count in units_per_segment.items()
    }
    result = list(labels)
    next_label = max(labels) + 1
    for group in sorted(set(labels)):
        members = [i for i, label in enumerate(labels) if label == group]
        share: dict[str, float] = defaultdict(float)
        for index in members:
            person = person_of_unit[index]
            if person:
                share[person] += seconds_of[owners[index]]
        candidates = sorted(
            (person for person, spoken in share.items() if spoken >= NAMED_SHARE_MIN_S),
            key=lambda person: -share[person],
        )
        if len(candidates) < 2:
            continue
        centroids = {
            person: normalize(units[[i for i in members if person_of_unit[i] == person]].sum(axis=0))
            for person in candidates
        }
        named: list[str] = []
        for person in candidates:
            if all(float(centroids[person] @ centroids[other]) < MERGE_THRESHOLD for other in named):
                named.append(person)
        if len(named) < 2:
            continue
        target_label: dict[str, int] = {}
        for position, person in enumerate(named):
            target_label[person] = group if position == 0 else next_label
            if position:
                next_label += 1
        for index in members:
            nearest = max(named, key=lambda person: float(units[index] @ centroids[person]))
            result[index] = target_label[nearest]
    return result


def _inherit_links(
    group_of: dict[str, int],
    by_id: dict[str, TranscriptSegment],
    links: dict[str, str | None],
) -> dict[int, str | None]:
    seconds: dict[int, Counter[str]] = defaultdict(Counter)
    for segment_id, group in group_of.items():
        segment = by_id[segment_id]
        person = links.get(segment.speaker_cluster or "")
        if person:
            seconds[group][person] += max(1, segment.end_ms - segment.start_ms)
    return {group: counter.most_common(1)[0][0] for group, counter in seconds.items() if counter}


def _units(order: list[str], frames_by_segment: dict[str, np.ndarray]) -> tuple[np.ndarray, list[str]]:
    total = sum(frames_by_segment[item].shape[0] for item in order)
    group = max(1, int(np.ceil(total / MAX_REFINE_FRAMES)))
    units: list[np.ndarray] = []
    owners: list[str] = []
    for segment_id in order:
        stack = frames_by_segment[segment_id]
        for lo in range(0, stack.shape[0], group):
            units.append(normalize(stack[lo : lo + group].sum(axis=0)))
            owners.append(segment_id)
    if not units:
        return np.zeros((0, 1), dtype=np.float32), []
    return np.stack(units).astype(np.float32), owners


def _read_wav(path: Path) -> np.ndarray | None:
    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getsampwidth() != 2 or handle.getframerate() != 16_000:
                return None
            raw = handle.readframes(handle.getnframes())
            channels = handle.getnchannels()
    except (OSError, wave.Error):
        return None
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data
