import type { Person, Segment } from "../api/types";
import { tr } from "../i18n/runtime";

/** Paleta de vozes: cada voz detectada ganha uma cor fixa na sessão. */
const VOICE_TOKENS = 8;

export interface RosterVoice {
  cluster: string;
  index: number;
  personId: string | null;
  name: string | null;
  talkMs: number;
  share: number;
  turns: number;
  firstMs: number;
  lastMs: number;
  confidence: number;
  sources: string[];
  hasVoiceprint: boolean;
}

export function clusterIndex(cluster: string | null | undefined): number | null {
  if (!cluster) return null;
  const digits = cluster.replace(/\D+/g, "");
  if (!digits) return null;
  const value = Number.parseInt(digits, 10);
  return Number.isFinite(value) ? value : null;
}

export function hashIndex(key: string): number {
  let hash = 0;
  for (let index = 0; index < key.length; index += 1) {
    hash = (hash * 31 + key.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
}

/** Variável CSS da cor da voz. Cluster vence: é a identidade acústica na sessão. */
export function voiceToken(segment: Pick<Segment, "speaker_cluster" | "speaker_id" | "source">): string {
  const index = clusterIndex(segment.speaker_cluster);
  if (index !== null) return `var(--voice-${((index - 1) % VOICE_TOKENS) + 1})`;
  if (segment.speaker_id) return `var(--voice-${(hashIndex(segment.speaker_id) % VOICE_TOKENS) + 1})`;
  return segment.source === "mic" ? "var(--channel-mic)" : "var(--channel-system)";
}

export function clusterToken(cluster: string): string {
  const index = clusterIndex(cluster) ?? hashIndex(cluster);
  return `var(--voice-${((index - 1 + VOICE_TOKENS) % VOICE_TOKENS) + 1})`;
}

export function voiceName(cluster: string | null | undefined): string {
  const index = clusterIndex(cluster);
  return tr("voices.voice", { n: index ?? "?" });
}

export function speakerName(segment: Segment, people: Person[]): string {
  const person = segment.speaker_id ? people.find((item) => item.id === segment.speaker_id) : undefined;
  if (person) return person.name;
  if (segment.speaker_name) return segment.speaker_name;
  if (segment.speaker_cluster) return voiceName(segment.speaker_cluster);
  if (segment.source === "mic") return tr("common.you");
  if (segment.source === "loopback") return tr("common.others");
  return tr("common.speaker");
}

/** Quem falou, quanto e quando — calculado direto dos trechos, sempre em sincronia com a tela. */
export function buildRoster(segments: Segment[], people: Person[]): RosterVoice[] {
  const byCluster = new Map<string, RosterVoice & { personVotes: Map<string, number>; confidenceSum: number; confidenceCount: number }>();
  let total = 0;
  for (const segment of segments) {
    const cluster = segment.speaker_cluster;
    if (!cluster) continue;
    const spoken = Math.max(0, segment.end_ms - segment.start_ms);
    total += spoken;
    let entry = byCluster.get(cluster);
    if (!entry) {
      entry = {
        cluster,
        index: clusterIndex(cluster) ?? 0,
        personId: null,
        name: null,
        talkMs: 0,
        share: 0,
        turns: 0,
        firstMs: segment.start_ms,
        lastMs: segment.end_ms,
        confidence: 0,
        sources: [],
        hasVoiceprint: false,
        personVotes: new Map(),
        confidenceSum: 0,
        confidenceCount: 0,
      };
      byCluster.set(cluster, entry);
    }
    entry.talkMs += spoken;
    entry.turns += 1;
    entry.firstMs = Math.min(entry.firstMs, segment.start_ms);
    entry.lastMs = Math.max(entry.lastMs, segment.end_ms);
    if (segment.source && !entry.sources.includes(segment.source)) entry.sources.push(segment.source);
    if (segment.speaker_id) {
      entry.personVotes.set(segment.speaker_id, (entry.personVotes.get(segment.speaker_id) ?? 0) + spoken + 1);
    }
    if (typeof segment.speaker_confidence === "number") {
      entry.confidenceSum += segment.speaker_confidence;
      entry.confidenceCount += 1;
    }
  }
  const roster: RosterVoice[] = [];
  for (const entry of byCluster.values()) {
    let best: string | null = null;
    let score = -1;
    for (const [personId, votes] of entry.personVotes) {
      if (votes > score) {
        best = personId;
        score = votes;
      }
    }
    const person = best ? people.find((item) => item.id === best) : undefined;
    roster.push({
      cluster: entry.cluster,
      index: entry.index,
      personId: best,
      name: person?.name ?? null,
      talkMs: entry.talkMs,
      share: total ? entry.talkMs / total : 0,
      turns: entry.turns,
      firstMs: entry.firstMs,
      lastMs: entry.lastMs,
      confidence: entry.confidenceCount ? entry.confidenceSum / entry.confidenceCount : 0,
      sources: entry.sources,
      hasVoiceprint: Boolean(person?.has_voiceprint),
    });
  }
  return roster.sort((a, b) => a.firstMs - b.firstMs);
}

/**
 * "Impressão vocal" desenhada: barras determinísticas a partir da chave da voz.
 * Não é o embedding real — é uma assinatura visual estável para cada voz.
 */
export function voiceprintBars(key: string, count = 18): number[] {
  let seed = hashIndex(key) || 7;
  const bars: number[] = [];
  for (let index = 0; index < count; index += 1) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    const noise = (seed % 1000) / 1000;
    const envelope = Math.sin((Math.PI * (index + 0.5)) / count);
    bars.push(0.18 + 0.82 * Math.min(1, envelope * (0.45 + 0.75 * noise)));
  }
  return bars;
}

export function countWords(segments: Segment[]): number {
  let words = 0;
  for (const segment of segments) {
    words += segment.text.split(/\s+/).filter(Boolean).length;
  }
  return words;
}

/**
 * Vozes que a pessoa atribuiu ao mesmo nome viram uma só na tela: mesma cor,
 * mesmo rótulo, uma linha na linha do tempo. Os dados gravados não mudam;
 * `members` diz quais vozes reais estão por trás de cada voz exibida.
 */
export function mergeVoicesByPerson(segments: Segment[]): { segments: Segment[]; members: Map<string, string[]> } {
  const votes = new Map<string, Map<string, number>>();
  for (const segment of segments) {
    if (!segment.speaker_cluster || !segment.speaker_id) continue;
    const byPerson = votes.get(segment.speaker_cluster) ?? new Map<string, number>();
    byPerson.set(segment.speaker_id, (byPerson.get(segment.speaker_id) ?? 0) + Math.max(1, segment.end_ms - segment.start_ms));
    votes.set(segment.speaker_cluster, byPerson);
  }
  const owner = new Map<string, string>();
  for (const [cluster, byPerson] of votes) {
    let best: string | null = null;
    let score = -1;
    for (const [person, value] of byPerson) {
      if (value > score) {
        best = person;
        score = value;
      }
    }
    if (best) owner.set(cluster, best);
  }
  const byPerson = new Map<string, string[]>();
  for (const [cluster, person] of owner) {
    const list = byPerson.get(person) ?? [];
    list.push(cluster);
    byPerson.set(person, list);
  }
  const canonical = new Map<string, string>();
  const members = new Map<string, string[]>();
  for (const clusters of byPerson.values()) {
    clusters.sort((a, b) => (clusterIndex(a) ?? 0) - (clusterIndex(b) ?? 0));
    const head = clusters[0];
    if (!head) continue;
    members.set(head, clusters);
    for (const cluster of clusters) canonical.set(cluster, head);
  }
  if (![...members.values()].some((list) => list.length > 1)) return { segments, members };
  return {
    segments: segments.map((segment) => {
      const head = segment.speaker_cluster ? canonical.get(segment.speaker_cluster) : undefined;
      return head && head !== segment.speaker_cluster ? { ...segment, speaker_cluster: head } : segment;
    }),
    members,
  };
}
