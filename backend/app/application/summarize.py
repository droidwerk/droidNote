from __future__ import annotations

import json
from datetime import UTC, datetime

from app.application.prompts import prompts_for, summary_context
from app.domain.models import ActionItem, Session, Summary, SummaryTopic, TranscriptSegment
from app.domain.ports import LlmPort, SessionRepository
from app.infrastructure.persistence.sqlite import new_id


class SummarizeService:
    def __init__(self, llm: LlmPort, store: SessionRepository) -> None:
        self._llm = llm
        self._store = store

    async def summarize(self, session_id: str) -> Summary:
        session = await self._require_session(session_id)
        segments = await self._store.list_segments(session_id)
        people = {item.id: item.name for item in await self._store.list_people()}
        transcript = render_transcript(segments, people)
        if not transcript:
            summary = self._empty_summary(session)
            await self._store.save_summary(summary)
            return summary
        participants = [
            person.name for person in await self._store.list_session_participants(session_id)
        ]
        context = summary_context(
            title=session.title,
            started_at=session.started_at.astimezone().strftime("%d/%m/%Y %H:%M"),
            participants=participants,
            duration=_duration(session, segments),
        )
        system, template = prompts_for(session.capture_mode)
        raw = await self._llm.generate_json(
            template.format(context=context, transcript=transcript),
            system=system,
        )
        parsed = parse_summary_json(raw)
        summary = Summary(
            id=new_id(),
            session_id=session.id,
            highlights=parsed["highlights"],
            decisions=parsed["decisions"],
            action_items=parsed["action_items"],
            raw_text=raw,
            created_at=datetime.now(tz=UTC),
            overview=parsed["overview"],
            topics=parsed["topics"],
            open_items=parsed["open_items"],
            language=parsed["language"] or session.language,
            notes_markdown=summary_to_markdown(session.title, parsed),
        )
        await self._store.save_summary(summary)
        return summary

    def _empty_summary(self, session: Session) -> Summary:
        return Summary(
            id=new_id(),
            session_id=session.id,
            highlights=[],
            decisions=[],
            action_items=[],
            raw_text="",
            created_at=datetime.now(tz=UTC),
            overview="Não há transcrição suficiente para gerar a ata.",
            topics=[],
            open_items=[],
            language=session.language,
            notes_markdown="",
        )

    async def _require_session(self, session_id: str) -> Session:
        session = await self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session


def render_transcript(segments: list[TranscriptSegment], people: dict[str, str]) -> str:
    lines: list[str] = []
    for item in segments:
        name = people.get(item.speaker_id or "")
        if not name:
            name = "Você" if item.source == "mic" else "Falante não identificado"
        lines.append(f"[{_clock(item.start_ms)}] {name}: {item.text}")
    return "\n".join(lines).strip()


def _clock(ms: int) -> str:
    total = max(0, ms) // 1000
    return f"{total // 60:02d}:{total % 60:02d}"


def _duration(session: Session, segments: list[TranscriptSegment]) -> str:
    if session.ended_at:
        seconds = int((session.ended_at - session.started_at).total_seconds())
    elif segments:
        seconds = segments[-1].end_ms // 1000
    else:
        seconds = 0
    minutes = max(0, seconds) // 60
    return f"{minutes} min" if minutes else "menos de 1 min"


def parse_summary_json(raw: str) -> dict:
    payload = _extract_json(raw)
    topics = _topics(payload.get("topics"))
    highlights = _string_list(payload.get("highlights"))
    if not highlights:
        highlights = [point for topic in topics for point in topic.points]
    language = payload.get("language")
    return {
        "overview": str(payload.get("overview") or "").strip(),
        "topics": topics,
        "highlights": highlights,
        "decisions": _string_list(payload.get("decisions")),
        "action_items": _action_items(payload.get("action_items")),
        "open_items": _string_list(payload.get("open_items")),
        "language": str(language).strip().lower()[:5] if language else None,
    }


def _topics(value: object) -> list[SummaryTopic]:
    if not isinstance(value, list):
        return []
    topics: list[SummaryTopic] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            topics.append(SummaryTopic(title=item.strip(), points=[]))
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        points = _string_list(item.get("points"))
        if not title and not points:
            continue
        topics.append(SummaryTopic(title=title or "Tópico", points=points))
    return topics


def _action_items(value: object) -> list[ActionItem]:
    if not isinstance(value, list):
        return []
    items: list[ActionItem] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(ActionItem(text=item.strip()))
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        items.append(
            ActionItem(
                text=text,
                owner=_optional(item.get("owner")),
                due=_optional(item.get("due")),
            )
        )
    return items


def _optional(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned or cleaned.lower() in {"null", "none", "não mencionado", "n/a", "-"}:
        return None
    return cleaned


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def summary_to_markdown(title: str, parsed: dict) -> str:
    lines = [f"# {title}", ""]
    overview = str(parsed.get("overview") or "").strip()
    if overview:
        lines.extend(["## Resumo", "", overview, ""])
    topics = parsed.get("topics") or []
    if topics:
        lines.extend(["## Assuntos", ""])
        for topic in topics:
            heading = topic.title if hasattr(topic, "title") else str(topic.get("title") or "")
            points = topic.points if hasattr(topic, "points") else list(topic.get("points") or [])
            if heading:
                lines.append(f"### {heading}")
            lines.extend([f"- {point}" for point in points])
            lines.append("")
    decisions = parsed.get("decisions") or []
    if decisions:
        lines.extend(["## Decisões", ""] + [f"- {item}" for item in decisions] + [""])
    actions = parsed.get("action_items") or []
    if actions:
        lines.append("## Ações")
        lines.append("")
        for item in actions:
            text = item.text if hasattr(item, "text") else str(item)
            owner = getattr(item, "owner", None)
            due = getattr(item, "due", None)
            extra = " — ".join(part for part in [owner, due] if part)
            lines.append(f"- {text}" + (f" ({extra})" if extra else ""))
        lines.append("")
    open_items = parsed.get("open_items") or []
    if open_items:
        lines.extend(["## Pendências", ""] + [f"- {item}" for item in open_items] + [""])
    return "\n".join(lines).strip() + "\n"
