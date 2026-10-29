from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Protocol

from app.application.prompts import prompts_for, summary_context
from app.domain.models import ActionItem, Session, Summary, SummaryTopic, TranscriptSegment
from app.domain.ports import LlmPort, SessionRepository
from app.infrastructure.persistence.sqlite import new_id


class TaskSync(Protocol):
    async def sync_from_summary(self, session_id: str, items: list[ActionItem]) -> object: ...


class PriorContext(Protocol):
    async def prior_context(self, session: Session) -> str: ...


class SummarizeService:
    def __init__(
        self,
        llm: LlmPort,
        store: SessionRepository,
        tasks: TaskSync | None = None,
        memory: PriorContext | None = None,
    ) -> None:
        self._llm = llm
        self._store = store
        self._tasks = tasks
        self._memory = memory

    async def summarize(self, session_id: str, template_id: str | None = None) -> Summary:
        session = await self._require_session(session_id)
        if template_id is not None:
            from dataclasses import replace as _replace

            session = _replace(session, template_id=template_id or None)
            await self._store.update_session(session)
        segments = await self._store.list_segments(session_id)
        people = {item.id: item.name for item in await self._store.list_people()}
        transcript = render_transcript(segments, people, session.language)
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
            voices=len({item.speaker_cluster for item in segments if item.speaker_cluster}),
        )
        context += await self._extras(session)
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
        await self._attach_note_context(session.id, parsed.get("user_notes") or [])
        if self._tasks is not None:
            await self._tasks.sync_from_summary(session.id, summary.action_items)
        return summary

    async def _attach_note_context(self, session_id: str, items: list[dict]) -> None:
        """O contexto que a IA escreveu para cada anotação vai para a própria anotação."""
        lister = getattr(self._store, "list_user_notes", None)
        setter = getattr(self._store, "set_note_context", None)
        if not callable(lister) or not callable(setter) or not items:
            return
        notes = await lister(session_id)
        used: set[str] = set()
        for item in items:
            context = str(item.get("context") or "").strip()
            wanted = _norm(str(item.get("note") or ""))
            if not context or not wanted:
                continue
            match = next((note for note in notes if note.id not in used and _norm(note.text) == wanted), None)
            if match is None:
                match = next(
                    (note for note in notes if note.id not in used and (wanted in _norm(note.text) or _norm(note.text) in wanted)),
                    None,
                )
            if match is not None:
                used.add(match.id)
                await setter(session_id, match.id, context)

    async def _extras(self, session: Session) -> str:
        """Template escolhido, citações e anotações da pessoa entram no pedido da ata."""
        parts: list[str] = [CITE_INSTRUCTIONS]
        if session.template_id:
            getter = getattr(self._store, "get_template", None)
            template = await getter(session.template_id) if callable(getter) else None
            if template is not None and template.kind == "note":
                parts.append(template_instructions(template.body))
        lister = getattr(self._store, "list_user_notes", None)
        notes = await lister(session.id) if callable(lister) else []
        if notes:
            parts.append(user_notes_instructions([(note.at_ms, note.text, note.kind) for note in notes]))
        parts.append(await self._support_material(session.id))
        if self._memory is not None:
            # Reuniões anteriores da série: a ata diz o que foi retomado, resolvido ou segue aberto.
            try:
                parts.append(await self._memory.prior_context(session))
            except Exception:
                pass
        return "".join(parts)

    async def _support_material(self, session_id: str) -> str:
        """Pauta, slides ou contrato que a pessoa subiu para esta conversa: nomes e termos certos na ata."""
        lister = getattr(self._store, "list_documents", None)
        first = getattr(self._store, "first_document_chunks", None)
        if not callable(lister) or not callable(first):
            return ""
        documents = await lister(session_id=session_id)
        if not documents:
            return ""
        budget = SUPPORT_MAX_CHARS
        blocks: list[str] = []
        per_doc = max(2, 10 // len(documents))
        for document in documents:
            lines = [f"### {document.name}"]
            for chunk in await first(document.id, per_doc):
                text = chunk.text.strip()
                if not text:
                    continue
                if len(text) > budget:
                    text = text[: max(0, budget - 1)] + "…"
                lines.append(text)
                budget -= len(text)
                if budget <= 0:
                    break
            blocks.append("\n".join(lines))
            if budget <= 0:
                break
        return SUPPORT_INSTRUCTIONS + "\n\n".join(blocks) + "\n\n"

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


VOICE_WORD = {
    "pt": "Voz",
    "en": "Speaker",
    "es": "Voz",
    "it": "Voce",
    "de": "Stimme",
    "fr": "Voix",
    "ru": "Голос",
}


def voice_label(cluster: str, language: str | None = None) -> str:
    """Rótulo de uma voz sem nome, no idioma da conversa ("Voz 2", "Speaker 2")."""
    digits = "".join(ch for ch in cluster if ch.isdigit()) or "?"
    word = VOICE_WORD.get((language or "pt")[:2].lower(), "Voz")
    return f"{word} {digits}"


def render_transcript(
    segments: list[TranscriptSegment],
    people: dict[str, str],
    language: str | None = None,
) -> str:
    lines: list[str] = []
    for item in segments:
        name = people.get(item.speaker_id or "")
        if not name and item.speaker_cluster:
            # Voz detectada e ainda sem nome: o modelo distingue quem disse o quê.
            name = voice_label(item.speaker_cluster, language or item.language)
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
    overview = _text(payload.get("overview"))
    # Modelos pequenos repetem a mesma frase em vários pontos (e o resumo dentro dos assuntos).
    topics = [
        SummaryTopic(title=topic.title, points=_unique(topic.points, skip=[overview]))
        for topic in _topics(payload.get("topics"))
    ]
    highlights = _unique(_string_list(payload.get("highlights")))
    if not highlights:
        highlights = _unique([point for topic in topics for point in topic.points])
    language = payload.get("language")
    return {
        "overview": overview,
        "topics": topics,
        "highlights": highlights,
        "decisions": _unique(_string_list(payload.get("decisions"))),
        "action_items": _action_items(payload.get("action_items")),
        "open_items": _unique(_string_list(payload.get("open_items"))),
        "language": str(language).strip().lower()[:5] if language else None,
        "user_notes": _user_notes(payload.get("user_notes")),
    }


def _user_notes(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    notes: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            notes.append({"note": item.strip(), "context": ""})
        elif isinstance(item, dict):
            note = str(item.get("note") or "").strip()
            if note:
                notes.append({"note": note, "context": _text(item.get("context"))})
    return notes


def template_instructions(body: str) -> str:
    sections = "\n".join(f"- {line.strip()}" for line in body.splitlines() if line.strip())
    return (
        "Estrutura pedida para \"topics\": use estas seções como títulos, nesta ordem. "
        "Deixe de fora a seção que a transcrição não cobre; nunca invente conteúdo para preenchê-la.\n"
        f"{sections}\n\n"
    )


SUPPORT_MAX_CHARS = 6_000
SUPPORT_INSTRUCTIONS = (
    "Material de apoio que a pessoa subiu para esta conversa (pauta, slides, contrato, apostila). Use-o para "
    "grafar nomes, siglas e termos técnicos do jeito certo e para reconhecer quando a conversa trata de um item "
    "dele; cite o item quando isso acontecer. Não resuma o material em si: a ata é sobre o que foi dito.\n"
)

CITE_INSTRUCTIONS = (
    "Citações: termine cada ponto dos assuntos, cada decisão, cada tarefa e cada pendência com o momento da "
    "transcrição que a sustenta, entre parênteses, no formato (mm:ss) — por exemplo \"Fechar o piloto (12:40)\". "
    "Use só horários que aparecem na transcrição.\n\n"
)
_STAMP = re.compile(r"\s*\((\d{1,2}:\d{2}(?::\d{2})?)\)")


def cite_markdown(text: str) -> str:
    """(12:40) vira `12:40`: a interface mostra como marca clicável que leva à fala."""
    return _STAMP.sub(lambda m: f" `{m.group(1)}`", text)


def strip_stamps(text: str) -> str:
    return _STAMP.sub("", text).strip()


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def _unique(items: list[str], skip: list[str] | None = None) -> list[str]:
    """Tira repetições (ignorando caixa, pontuação e o horário citado) e frases iguais às de `skip`."""
    seen = {_norm(strip_stamps(item)) for item in skip or [] if item}
    out: list[str] = []
    for item in items:
        key = _norm(strip_stamps(item))
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


NOTE_KIND_LABELS = {"decision": "DECISÃO", "task": "TAREFA", "important": "IMPORTANTE", "question": "DÚVIDA"}


def user_notes_instructions(notes: list[tuple]) -> str:
    rows = []
    for item in notes:
        at_ms, text = item[0], item[1]
        kind = item[2] if len(item) > 2 else None
        tag = f" [{NOTE_KIND_LABELS[kind]}]" if kind in NOTE_KIND_LABELS else ""
        rows.append(f"[{_clock(at_ms)}]{tag} {text}")
    lines = "\n".join(rows)
    return (
        "Anotações que a pessoa digitou durante a conversa, com o momento. Elas mostram o que importa para ela: "
        "garanta que cada uma esteja coberta na ata. As marcadas [DECISÃO] entram em \"decisions\", as [TAREFA] "
        "em \"action_items\" (com dono e prazo se foram ditos), as [DÚVIDA] em \"open_items\", e as "
        "[IMPORTANTE] ganham destaque. Responda também a chave \"user_notes\": array de "
        "{\"note\": a anotação como foi escrita, \"context\": 1 a 3 frases com o que foi dito em torno daquele "
        "momento, só com base na transcrição}.\n"
        f"{lines}\n\n"
    )


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


def _text(value: object) -> str:
    """Campo de texto que o modelo às vezes devolve como lista de frases: vira um parágrafo."""
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def summary_to_markdown(title: str, parsed: dict) -> str:
    """Ata em Markdown. As anotações da pessoa não entram aqui: elas aparecem no
    documento da sessão, cada uma com o contexto que a IA encontrou."""
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
    return cite_markdown("\n".join(lines).strip()) + "\n"
