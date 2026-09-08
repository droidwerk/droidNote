from __future__ import annotations

import json
import re
from dataclasses import replace

from app.application.prompts import SPEAKER_ASSIGN_PROMPT
from app.domain.models import Person, TranscriptSegment
from app.domain.ports import LlmPort, SessionRepository

_PREFIX = re.compile(
    r"^\s*(?P<name>.+?)\s*[:\-–]\s+(?P<body>.+)$",
    re.DOTALL,
)
UNSET = object()


def peel_speaker_prefix(text: str, people: list[Person]) -> tuple[str, str | None]:
    cleaned = (text or "").strip()
    if not cleaned or not people:
        return cleaned, None
    ranked = sorted(people, key=lambda item: len(item.name), reverse=True)
    lowered = cleaned.lower()
    for person in ranked:
        token = person.name.strip()
        if len(token) < 2:
            continue
        prefix = token.lower()
        if lowered.startswith(prefix):
            rest = cleaned[len(token) :]
            if rest and rest[0].isalnum():
                continue
            body = rest.lstrip(" \t:-–")
            if body and body != cleaned:
                return body.strip(), person.id
    match = _PREFIX.match(cleaned)
    if not match:
        return cleaned, None
    guessed = match.group("name").strip().lower()
    body = match.group("body").strip()
    for person in ranked:
        if person.name.strip().lower() == guessed:
            return body, person.id
    return cleaned, None


class SpeakersService:
    def __init__(self, llm: LlmPort, store: SessionRepository) -> None:
        self._llm = llm
        self._store = store

    async def list_people(self) -> list[Person]:
        return await self._store.list_people()

    async def name_map(self) -> dict[str, str]:
        return {item.id: item.name for item in await self._store.list_people()}

    async def create_person(self, name: str) -> Person:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Nome vazio")
        return await self._store.create_person(cleaned)

    async def delete_person(self, person_id: str) -> None:
        await self._store.delete_person(person_id)

    async def participants(self, session_id: str) -> list[Person]:
        return await self._store.list_session_participants(session_id)

    async def set_participants(self, session_id: str, person_ids: list[str]) -> list[Person]:
        people = await self._store.list_people_by_ids(person_ids)
        await self._store.set_session_participants(session_id, [item.id for item in people])
        return people

    async def patch_segment(
        self,
        session_id: str,
        segment_id: str,
        *,
        speaker_id: str | None | object = UNSET,
        name: str | None = None,
        text: str | None = None,
        apply_forward: bool = False,
    ) -> TranscriptSegment:
        segment = await self._store.get_segment(segment_id)
        if segment is None or segment.session_id != session_id:
            raise KeyError(segment_id)
        person_id = segment.speaker_id
        if name and name.strip():
            person = await self._store.create_person(name.strip())
            person_id = person.id
            await self._ensure_participant(session_id, person.id)
        elif speaker_id is not UNSET:
            if speaker_id in (None, ""):
                person_id = None
            else:
                chosen = str(speaker_id)
                person = await self._store.get_person(chosen)
                if person is None:
                    raise KeyError(chosen)
                person_id = chosen
                await self._ensure_participant(session_id, person.id)
        next_text = segment.text if text is None else text.strip()
        if not next_text:
            next_text = segment.text
        updated = await self._store.save_segment(
            replace(segment, speaker_id=person_id, text=next_text)
        )
        if updated is None:
            raise KeyError(segment_id)
        if apply_forward and person_id:
            await self._fill_forward(session_id, updated.start_ms, person_id, updated.source)
        return updated

    async def assign_from_context(self, session_id: str) -> list[TranscriptSegment]:
        people = await self._store.list_session_participants(session_id)
        if not people:
            people = await self._store.list_people()
        segments = await self._store.list_segments(session_id)
        if not people or not segments:
            return segments
        if len(people) == 1:
            only = people[0].id
            for item in segments:
                if item.speaker_id:
                    continue
                await self._store.set_segment_speaker(item.id, only)
            return await self._store.list_segments(session_id)
        sticky: str | None = None
        for item in segments:
            if item.source == "mic":
                continue
            if item.speaker_id:
                sticky = item.speaker_id
                continue
            text, parsed = peel_speaker_prefix(item.text, people)
            chosen = parsed or sticky
            if parsed and text != item.text:
                await self._store.save_segment(replace(item, text=text, speaker_id=chosen))
                sticky = chosen
            elif chosen:
                await self._store.set_segment_speaker(item.id, chosen)
                sticky = chosen
        pending = [
            item
            for item in await self._store.list_segments(session_id)
            if not item.speaker_id and item.source != "mic"
        ]
        if not pending:
            return await self._store.list_segments(session_id)
        people_lines = "\n".join(f"- {item.id}: {item.name}" for item in people)
        segment_lines = "\n".join(f"- {item.id}: {item.text}" for item in pending)
        try:
            raw = await self._llm.generate_json(
                SPEAKER_ASSIGN_PROMPT.format(people=people_lines, segments=segment_lines)
            )
        except Exception:
            return await self._store.list_segments(session_id)
        allowed = {item.id for item in people}
        remaining = {item.id for item in pending}
        for segment_id, person_id in _parse_assignments(raw):
            if person_id not in allowed or segment_id not in remaining:
                continue
            await self._store.set_segment_speaker(segment_id, person_id)
        return await self._store.list_segments(session_id)

    async def _ensure_participant(self, session_id: str, person_id: str) -> None:
        existing = await self._store.list_session_participants(session_id)
        ids = [item.id for item in existing]
        if person_id in ids:
            return
        ids.append(person_id)
        await self._store.set_session_participants(session_id, ids)

    async def _fill_forward(
        self,
        session_id: str,
        after_ms: int,
        speaker_id: str,
        source: str | None = None,
    ) -> None:
        for item in await self._store.list_segments(session_id):
            if item.start_ms <= after_ms:
                continue
            if source and item.source and item.source != source:
                continue
            if item.speaker_id:
                if not source or item.source == source:
                    break
                continue
            await self._store.set_segment_speaker(item.id, speaker_id)


def _parse_assignments(raw: str) -> list[tuple[str, str]]:
    payload = _extract_json(raw)
    rows = payload.get("assignments")
    if not isinstance(rows, list):
        return []
    result: list[tuple[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        segment_id = str(item.get("segment_id") or "").strip()
        person_id = item.get("person_id")
        if not segment_id or not person_id:
            continue
        result.append((segment_id, str(person_id).strip()))
    return result


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(text[start : end + 1])
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            return {}
    return {}
