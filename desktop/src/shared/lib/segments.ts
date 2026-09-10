import type { Person, Segment } from "../api/types";
import { tr } from "../i18n/runtime";
import { formatClock } from "./format";

export function mergeSegmentLists(current: Segment[], incoming: Segment[]): Segment[] {
  const map = new Map<string, Segment>();
  for (const item of current) map.set(item.id, item);
  for (const item of incoming) {
    const existing = map.get(item.id);
    if (existing?.speaker_id && !item.speaker_id) {
      map.set(item.id, {
        ...item,
        speaker_id: existing.speaker_id,
        speaker_name: existing.speaker_name ?? item.speaker_name,
      });
    } else {
      map.set(item.id, item);
    }
  }
  return [...map.values()].sort((a, b) => a.start_ms - b.start_ms);
}

export function mergeSessionSegments(
  saved: Segment[],
  live: Segment[],
  sessionId: string | null,
): Segment[] {
  const scoped = sessionId ? live.filter((item) => item.session_id === sessionId) : live;
  return mergeSegmentLists(saved, scoped);
}

export function speakerLabel(segment: Segment, people: Person[]): string {
  const found = people.find((item) => item.id === segment.speaker_id);
  if (found) return found.name;
  if (segment.speaker_name) return segment.speaker_name;
  if (segment.source === "mic") return tr("common.you");
  if (segment.source === "loopback") return tr("common.others");
  return tr("common.speaker");
}

export function formatPlain(segment: Segment, people: Person[]): string {
  const { body } = splitScene(segment.text);
  return `${speakerLabel(segment, people)} · ${formatClock(segment.start_ms)}\n${body}`;
}

export function splitScene(text: string): { label: string | null; body: string } {
  const match = /^\[([^\]]+)\]\s*/.exec(text);
  if (!match) return { label: null, body: text };
  return { label: match[1] ?? null, body: text.slice(match[0].length) };
}

export function resolveSpeaker(segment: Segment, people: Person[]): Person | null {
  if (!segment.speaker_id) return null;
  const found = people.find((item) => item.id === segment.speaker_id);
  if (found) return found;
  return { id: segment.speaker_id, name: segment.speaker_name || tr("common.speaker") };
}

export function groupTurns(segments: Segment[]): Segment[][] {
  const turns: Segment[][] = [];
  for (const item of segments) {
    const previous = turns.length > 0 ? turns[turns.length - 1] : undefined;
    const last = previous && previous.length > 0 ? previous[previous.length - 1] : undefined;
    if (
      previous &&
      last &&
      (last.source ?? "") === (item.source ?? "") &&
      (last.speaker_id ?? "") === (item.speaker_id ?? "")
    ) {
      previous.push(item);
    } else {
      turns.push([item]);
    }
  }
  return turns;
}
