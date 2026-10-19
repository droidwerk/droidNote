"""Quem falou cada palavra de uma janela de áudio.

1. Embeddings em janelas deslizantes de 1,5 s (passo 0,75 s), num lote só.
2. Agrupamento local dentro da janela; cada grupo vira uma voz da sessão
   pelo `SpeakerTracker` (que também reconhece impressões vocais salvas).
3. Cada palavra do Whisper recebe a voz que cobre o seu meio.
4. Palavras consecutivas da mesma voz viram um turno. Turnos curtos demais
   são absorvidos pelo vizinho para não picotar a transcrição.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.infrastructure.voice.embedder import normalize
from app.infrastructure.voice.fbank import FRAME_SHIFT, cmn, fbank
from app.infrastructure.voice.tracker import SpeakerTracker, agglomerate

SUB_WINDOW_S = 1.5
SUB_HOP_S = 0.75
LOCAL_THRESHOLD = 0.58
MIN_SPEECH_RATIO = 0.4
MIN_TURN_S = 0.9
MIN_TURN_WORDS = 3


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    text: str
    cluster: str | None
    person_id: str | None
    similarity: float
    embedding: np.ndarray | None
    seconds: float
    frames: np.ndarray | None = None


@dataclass
class _Core:
    start: float
    end: float
    embedding: np.ndarray
    cluster: str | None = None
    person_id: str | None = None
    similarity: float = 0.0


def window_embeddings(
    embedder: object,
    samples: np.ndarray,
    speech: np.ndarray | None = None,
) -> list[_Core]:
    """Embeddings por janela deslizante. Cada item cobre o miolo da sua janela."""
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    seconds = audio.size / 16_000
    if seconds < 0.6:
        return []
    batch_embed = getattr(embedder, "embed_batch", None)
    if seconds < SUB_WINDOW_S + SUB_HOP_S or not callable(batch_embed):
        vector = embedder.embed(audio)  # type: ignore[attr-defined]
        if vector is None:
            return []
        return [_Core(0.0, seconds, vector)]
    model = getattr(embedder, "model", None)
    window_kind = getattr(model, "window", "povey")
    scale = float(getattr(model, "scale", 1.0))
    features = fbank(audio, window=window_kind, scale=scale)
    per_second = 16_000 // FRAME_SHIFT
    width = int(SUB_WINDOW_S * per_second)
    hop = int(SUB_HOP_S * per_second)
    starts = list(range(0, max(1, features.shape[0] - width + 1), hop))
    if starts and starts[-1] + width < features.shape[0]:
        starts.append(features.shape[0] - width)
    chosen: list[int] = []
    for start in starts:
        if speech is not None and speech.size:
            lo = int(start * FRAME_SHIFT)
            hi = min(speech.size, int((start + width) * FRAME_SHIFT))
            ratio = float(np.mean(speech[lo:hi])) if hi > lo else 0.0
            if ratio < MIN_SPEECH_RATIO:
                continue
        chosen.append(start)
    if not chosen:
        return []
    stack = np.stack([cmn(features[start : start + width]) for start in chosen]).astype(np.float32)
    vectors = batch_embed(stack)
    if vectors is None:
        return []
    cores: list[_Core] = []
    half_gap = (SUB_WINDOW_S - SUB_HOP_S) / 2.0
    for start, vector in zip(chosen, vectors):
        begin = start / per_second
        cores.append(_Core(begin + half_gap, begin + half_gap + SUB_HOP_S, normalize(vector)))
    if cores:
        cores[0].start = min(cores[0].start, chosen[0] / per_second)
        cores[-1].end = max(cores[-1].end, chosen[-1] / per_second + SUB_WINDOW_S)
    return cores


def diarize_window(
    embedder: object,
    tracker: SpeakerTracker,
    samples: np.ndarray,
    words: Sequence[Word],
    *,
    source: str | None = None,
    offset_ms: int = 0,
    speech: np.ndarray | None = None,
) -> list[Turn]:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    cores = window_embeddings(embedder, audio, speech)
    if not words:
        return []
    if not cores:
        text = _join([item.text for item in words])
        return [Turn(words[0].start, words[-1].end, text, None, None, 0.0, None, 0.0)]

    labels = agglomerate([item.embedding for item in cores], threshold=LOCAL_THRESHOLD)
    groups: dict[int, list[_Core]] = {}
    for core, label in zip(cores, labels):
        groups.setdefault(label, []).append(core)
    for members in sorted(groups.values(), key=lambda items: -len(items)):
        centroid = normalize(np.sum([item.embedding for item in members], axis=0))
        seconds = sum(item.end - item.start for item in members)
        at_ms = offset_ms + int(members[0].start * 1000)
        match = tracker.assign(centroid, seconds, source, at_ms)
        for item in members:
            if match is None:
                continue
            item.cluster = match.cluster
            item.person_id = match.person_id
            item.similarity = float(np.dot(item.embedding, centroid)) if seconds else match.similarity
    _fill_unlabeled(cores)

    def core_at(moment: float) -> _Core:
        best = cores[0]
        distance = float("inf")
        for core in cores:
            if core.start <= moment < core.end:
                return core
            gap = min(abs(moment - core.start), abs(moment - core.end))
            if gap < distance:
                best, distance = core, gap
        return best

    tagged: list[tuple[Word, _Core]] = []
    for word in words:
        middle = (word.start + word.end) / 2.0
        tagged.append((word, core_at(middle)))

    turns: list[list[tuple[Word, _Core]]] = []
    for word, core in tagged:
        if turns and turns[-1][-1][1].cluster == core.cluster:
            turns[-1].append((word, core))
        else:
            turns.append([(word, core)])
    turns = _absorb_short(turns)

    result: list[Turn] = []
    for chunk in turns:
        start = chunk[0][0].start
        end = max(item[0].end for item in chunk)
        inside = [core for core in cores if core.end > start and core.start < end and core.cluster == chunk[0][1].cluster]
        if not inside:
            inside = [chunk[0][1]]
        frames = np.stack([core.embedding for core in inside]).astype(np.float32)
        embedding = normalize(frames.sum(axis=0))
        similarity = float(np.mean([core.similarity for core in inside]))
        head = chunk[0][1]
        result.append(
            Turn(
                start=start,
                end=end,
                text=_join([item[0].text for item in chunk]),
                cluster=head.cluster,
                person_id=head.person_id,
                similarity=similarity,
                embedding=embedding,
                seconds=max(0.0, end - start),
                frames=frames,
            )
        )
    return [item for item in result if item.text]


def _fill_unlabeled(cores: list[_Core]) -> None:
    labeled = [index for index, core in enumerate(cores) if core.cluster]
    if not labeled:
        return
    for index, core in enumerate(cores):
        if core.cluster:
            continue
        nearest = min(labeled, key=lambda other: abs(other - index))
        core.cluster = cores[nearest].cluster
        core.person_id = cores[nearest].person_id
        core.similarity = cores[nearest].similarity


def _absorb_short(turns: list[list[tuple[Word, _Core]]]) -> list[list[tuple[Word, _Core]]]:
    changed = True
    while changed and len(turns) > 1:
        changed = False
        for index, chunk in enumerate(turns):
            duration = max(item[0].end for item in chunk) - chunk[0][0].start
            if duration >= MIN_TURN_S or len(chunk) >= MIN_TURN_WORDS:
                continue
            target = index - 1 if index > 0 else index + 1
            other = turns[target]
            head = other[0][1]
            merged = [(word, head) for word, _ in chunk]
            if target < index:
                turns[target] = other + merged
            else:
                turns[target] = merged + other
            del turns[index]
            changed = True
            break
        # Turnos vizinhos que ficaram com a mesma voz depois da absorção.
        joined: list[list[tuple[Word, _Core]]] = []
        for chunk in turns:
            if joined and joined[-1][-1][1].cluster == chunk[0][1].cluster:
                joined[-1].extend(chunk)
            else:
                joined.append(chunk)
        turns = joined
    return turns


def _join(parts: Sequence[str]) -> str:
    text = ""
    for part in parts:
        piece = part if part.startswith(" ") or not text else f" {part}"
        text += piece
    return " ".join(text.split()).strip()
