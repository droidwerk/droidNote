"""Agrupamento de vozes: ao vivo (incremental) e depois da gravação (aglomerativo).

Limiares calibrados com o WeSpeaker ResNet34-LM: trechos da mesma pessoa ficam
em ~0,6 de cosseno entre si e ~0,75 contra o centróide; pessoas diferentes
ficam abaixo de ~0,45.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

from app.infrastructure.voice.embedder import normalize

# Calibrado em gravações reais (medição em scratchpad/tools/measure_voices.py):
# falas inteiras da mesma pessoa ficam em mediana 0,73–0,83 com p10 0,42–0,54;
# pessoas diferentes nunca passaram de 0,51 (centróides entre 0,14 e 0,28).
LIVE_THRESHOLD = 0.5
OFFLINE_THRESHOLD = 0.45
KNOWN_THRESHOLD = 0.58
SHORT_SECONDS = 1.2
SHORT_MARGIN = 0.06
# Abaixo disso um trecho não funda voz nova: ou vai para a voz mais parecida
# (se passar de PROVISIONAL_THRESHOLD) ou herda a do vizinho. Vozes fantasmas
# nasciam de falas de 1–2 s com impressão ruim.
NEW_VOICE_MIN_S = 2.5
PROVISIONAL_THRESHOLD = 0.35
MERGE_THRESHOLD = 0.45
MIN_CLUSTER_UNITS = 3
SINGLE_VOICE_FLOOR = 0.42
PRUNE_RATIOS = (0.05, 0.1, 0.15, 0.25, 0.35)
MIN_PRUNE = 4


@dataclass
class VoiceCluster:
    key: str
    index: int
    total: np.ndarray
    seconds: float = 0.0
    person_id: str | None = None
    sources: Counter[str] = field(default_factory=Counter)
    first_ms: int = 0

    @property
    def centroid(self) -> np.ndarray:
        return normalize(self.total)

    def add(self, embedding: np.ndarray, seconds: float, source: str | None) -> None:
        weight = float(min(max(seconds, 0.3), 12.0))
        self.total = self.total + embedding * weight
        self.seconds += float(seconds)
        if source:
            self.sources[source] += 1


@dataclass(frozen=True)
class VoiceMatch:
    cluster: str
    person_id: str | None
    similarity: float
    created: bool = False


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    a = normalize(left)
    b = normalize(right)
    if a.size != b.size or a.size == 0:
        return -1.0
    return float(np.dot(a, b))


class SpeakerTracker:
    """Vozes de uma sessão. Uma instância por gravação."""

    def __init__(
        self,
        known: dict[str, np.ndarray] | None = None,
        *,
        threshold: float = LIVE_THRESHOLD,
        known_threshold: float = KNOWN_THRESHOLD,
    ) -> None:
        self.threshold = threshold
        self.known_threshold = known_threshold
        self.known = {key: normalize(value) for key, value in (known or {}).items()}
        self.clusters: dict[str, VoiceCluster] = {}
        self._next = 1

    def restore(self, key: str, embedding: np.ndarray, seconds: float, person_id: str | None, source: str | None, at_ms: int = 0) -> None:
        """Recarrega uma voz já gravada (retomar sessão ou reanalisar)."""
        cluster = self.clusters.get(key)
        if cluster is None:
            index = _key_index(key) or self._next
            cluster = VoiceCluster(key=key, index=index, total=np.zeros_like(embedding), first_ms=at_ms)
            self.clusters[key] = cluster
            self._next = max(self._next, index + 1)
        cluster.add(embedding, seconds, source)
        if person_id and not cluster.person_id:
            cluster.person_id = person_id

    def best_cluster(self, embedding: np.ndarray) -> tuple[VoiceCluster | None, float]:
        best: VoiceCluster | None = None
        score = -1.0
        for cluster in self.clusters.values():
            value = float(np.dot(cluster.centroid, embedding))
            if value > score:
                best, score = cluster, value
        return best, score

    def best_person(self, embedding: np.ndarray) -> tuple[str | None, float]:
        best: str | None = None
        score = -1.0
        for person_id, print_ in self.known.items():
            if print_.size != embedding.size:
                continue
            value = float(np.dot(print_, embedding))
            if value > score:
                best, score = person_id, value
        return best, score

    def assign(self, embedding: np.ndarray, seconds: float, source: str | None = None, at_ms: int = 0) -> VoiceMatch | None:
        vector = normalize(embedding)
        cluster, sim_cluster = self.best_cluster(vector)
        person, sim_person = self.best_person(vector)
        short = seconds < SHORT_SECONDS
        threshold = self.threshold - (SHORT_MARGIN if short else 0.0)

        if cluster is not None and sim_cluster >= threshold:
            if not short:
                cluster.add(vector, seconds, source)
            if cluster.person_id is None and person and sim_person >= self.known_threshold:
                cluster.person_id = person
            return VoiceMatch(cluster.key, cluster.person_id, sim_cluster)

        if person and sim_person >= self.known_threshold:
            linked = next((item for item in self.clusters.values() if item.person_id == person), None)
            if linked is not None:
                if not short:
                    linked.add(vector, seconds, source)
                return VoiceMatch(linked.key, person, sim_person)
            created = self._create(vector, seconds, source, at_ms, person)
            return VoiceMatch(created.key, person, sim_person, created=True)

        if short:
            # Trecho curto demais para fundar uma voz nova: herda do vizinho.
            return None
        if seconds < NEW_VOICE_MIN_S and self.clusters:
            # Pouca fala para uma voz própria: fica provisoriamente com a mais
            # parecida (sem somar ao centróide) ou herda do vizinho.
            if cluster is not None and sim_cluster >= PROVISIONAL_THRESHOLD:
                return VoiceMatch(cluster.key, cluster.person_id, sim_cluster)
            return None
        created = self._create(vector, seconds, source, at_ms, None)
        return VoiceMatch(created.key, None, 1.0, created=True)

    def link(self, key: str, person_id: str | None) -> None:
        cluster = self.clusters.get(key)
        if cluster is not None:
            cluster.person_id = person_id

    def label(self, key: str | None) -> int | None:
        if not key:
            return None
        cluster = self.clusters.get(key)
        return cluster.index if cluster else _key_index(key)

    def _create(self, vector: np.ndarray, seconds: float, source: str | None, at_ms: int, person: str | None) -> VoiceCluster:
        index = self._next
        self._next += 1
        cluster = VoiceCluster(key=f"v{index}", index=index, total=np.zeros_like(vector), first_ms=at_ms, person_id=person)
        cluster.add(vector, max(seconds, 0.3), source)
        self.clusters[cluster.key] = cluster
        return cluster


def agglomerate(
    embeddings: Sequence[np.ndarray],
    weights: Sequence[float] | None = None,
    *,
    threshold: float = OFFLINE_THRESHOLD,
) -> list[int]:
    """Clusterização aglomerativa por centróide. Devolve o rótulo de cada item."""
    count = len(embeddings)
    if count == 0:
        return []
    weight = [max(0.3, min(float(w), 12.0)) for w in (weights or [1.0] * count)]
    totals = [normalize(item) * w for item, w in zip(embeddings, weight)]
    members: list[list[int]] = [[index] for index in range(count)]
    while len(members) > 1:
        cents = np.stack([normalize(item) for item in totals])
        sims = cents @ cents.T
        np.fill_diagonal(sims, -2.0)
        i, j = np.unravel_index(int(np.argmax(sims)), sims.shape)
        if sims[i, j] < threshold:
            break
        if i > j:
            i, j = j, i
        members[i].extend(members[j])
        totals[i] = totals[i] + totals[j]
        del members[j]
        del totals[j]
    labels = [0] * count
    for label, group in enumerate(members):
        for index in group:
            labels[index] = label
    return labels


def spectral_labels(
    embeddings: Sequence[np.ndarray],
    weights: Sequence[float] | None = None,
    *,
    max_speakers: int = 10,
    merge_threshold: float = MERGE_THRESHOLD,
) -> list[int]:
    """Clusterização espectral com número de vozes estimado pelo eigengap.

    Visão global da sessão: fragmentos ruidosos da mesma pessoa formam um bloco
    na matriz de afinidade mesmo quando a similaridade par-a-par é baixa, coisa
    que nenhum limiar fixo enxerga. Depois, grupos com centróides muito
    parecidos são fundidos.
    """
    count = len(embeddings)
    if count == 0:
        return []
    if count == 1:
        return [0]
    matrix = np.stack([normalize(item) for item in embeddings]).astype(np.float64)
    sims = np.clip(matrix @ matrix.T, -1.0, 1.0)
    if count <= 3:
        return agglomerate(list(matrix), weights, threshold=merge_threshold)
    off_diag = sims[~np.eye(count, dtype=bool)]
    if float(np.percentile(off_diag, 10)) >= SINGLE_VOICE_FLOOR:
        return [0] * count

    # NME-SC: para cada poda p, o maior eigengap normalizado g_p; fica a poda
    # com menor p / g_p. k = 1 nunca sai do eigengap (λ0 é sempre zero): uma
    # voz só aparece quando a fusão de centróides junta tudo no fim.
    limit = min(max_speakers, count - 1)
    best: tuple[float, int, np.ndarray] | None = None
    for ratio in PRUNE_RATIOS:
        keep = min(count - 1, max(MIN_PRUNE, int(round(count * ratio))))
        affinity = _pruned_affinity(sims, keep)
        laplacian = np.diag(affinity.sum(axis=1)) - affinity
        values, vectors = np.linalg.eigh(laplacian)
        gaps = np.diff(values[: limit + 1])[1:]
        if gaps.size == 0:
            continue
        clusters = int(np.argmax(gaps)) + 2
        normalized = float(gaps.max() / (values[limit] + 1e-6))
        if normalized <= 0:
            continue
        score = keep / normalized
        if best is None or score < best[0]:
            best = (score, clusters, vectors[:, :clusters])
    if best is None:
        return agglomerate(list(matrix), weights, threshold=merge_threshold)
    labels = _dissolve_islands(matrix, _kmeans(best[2], best[1]))
    return _merge_close(matrix, labels, weights, merge_threshold)


def _dissolve_islands(matrix: np.ndarray, labels: list[int]) -> list[int]:
    """Grupo com menos de MIN_CLUSTER_UNITS unidades não é uma voz: é uma fala
    com impressão ruim. Vai para o grupo de centróide mais próximo."""
    counts = Counter(labels)
    big = [group for group, count in counts.items() if count >= MIN_CLUSTER_UNITS]
    if not big or len(big) == len(counts):
        return labels
    centroids = {group: normalize(matrix[[i for i, item in enumerate(labels) if item == group]].sum(axis=0)) for group in big}
    result = list(labels)
    for index, group in enumerate(labels):
        if group in centroids:
            continue
        result[index] = max(big, key=lambda candidate: float(matrix[index] @ centroids[candidate]))
    return result


def _pruned_affinity(sims: np.ndarray, keep: int) -> np.ndarray:
    affinity = np.maximum(sims, 0.0).copy()
    np.fill_diagonal(affinity, 0.0)
    count = affinity.shape[0]
    for row in range(count):
        if keep >= count - 1:
            break
        cutoff = np.partition(affinity[row], count - keep)[count - keep]
        affinity[row, affinity[row] < cutoff] = 0.0
    affinity = 0.5 * (affinity + affinity.T)
    np.fill_diagonal(affinity, 1.0)
    return affinity


def _kmeans(points: np.ndarray, clusters: int, rounds: int = 8) -> list[int]:
    data = points / np.maximum(np.linalg.norm(points, axis=1, keepdims=True), 1e-9)
    rng = np.random.default_rng(7)
    best: tuple[float, np.ndarray] | None = None
    for _ in range(rounds):
        centers = [data[int(rng.integers(len(data)))]]
        while len(centers) < clusters:
            dist = np.min([np.sum((data - center) ** 2, axis=1) for center in centers], axis=0)
            total = float(dist.sum())
            if total <= 0:
                centers.append(data[int(rng.integers(len(data)))])
                continue
            centers.append(data[int(rng.choice(len(data), p=dist / total))])
        stack = np.stack(centers)
        assign = np.zeros(len(data), dtype=int)
        for _ in range(50):
            dist = ((data[:, None, :] - stack[None, :, :]) ** 2).sum(axis=2)
            new_assign = np.argmin(dist, axis=1)
            if np.array_equal(new_assign, assign):
                break
            assign = new_assign
            for index in range(clusters):
                members = data[assign == index]
                if len(members):
                    stack[index] = members.mean(axis=0)
        inertia = float(((data - stack[assign]) ** 2).sum())
        if best is None or inertia < best[0]:
            best = (inertia, assign.copy())
    assert best is not None
    return [int(item) for item in best[1]]


def _merge_close(
    matrix: np.ndarray,
    labels: list[int],
    weights: Sequence[float] | None,
    threshold: float,
) -> list[int]:
    groups = sorted(set(labels))
    weight = list(weights) if weights is not None else [1.0] * len(labels)
    centroids = {
        group: normalize(
            np.sum([matrix[i] * max(0.3, float(weight[i])) for i, label in enumerate(labels) if label == group], axis=0)
        )
        for group in groups
    }
    mapping = {group: group for group in groups}
    merged = True
    while merged:
        merged = False
        live = sorted(set(mapping.values()))
        best: tuple[float, int, int] | None = None
        for a_index, left in enumerate(live):
            for right in live[a_index + 1 :]:
                value = float(np.dot(centroids[left], centroids[right]))
                if value >= threshold and (best is None or value > best[0]):
                    best = (value, left, right)
        if best is not None:
            _, left, right = best
            for key, target in mapping.items():
                if target == right:
                    mapping[key] = left
            members = [i for i, label in enumerate(labels) if mapping[label] == left]
            centroids[left] = normalize(np.sum([matrix[i] for i in members], axis=0))
            merged = True
    ordered: dict[int, int] = {}
    result: list[int] = []
    for label in labels:
        target = mapping[label]
        if target not in ordered:
            ordered[target] = len(ordered)
        result.append(ordered[target])
    return result


def blend_voiceprint(current: np.ndarray | None, samples: int, additions: Iterable[tuple[np.ndarray, float]], cap: int = 40) -> tuple[np.ndarray, int]:
    """Atualiza a impressão vocal de uma pessoa com novos trechos rotulados."""
    total = np.zeros(0, dtype=np.float32)
    count = 0
    if current is not None and current.size:
        prior = min(samples, cap)
        total = normalize(current) * float(max(prior, 1))
        count = samples
    for embedding, seconds in additions:
        vector = normalize(embedding)
        weight = float(min(max(seconds, 0.5), 10.0)) / 3.0
        total = vector * weight if total.size == 0 else total + vector * weight
        count += 1
    return normalize(total), count


def _key_index(key: str) -> int | None:
    digits = "".join(ch for ch in key if ch.isdigit())
    return int(digits) if digits else None
