"""Memória entre reuniões: o fio que liga esta conversa às anteriores da mesma série.

Antes da reunião (sem ata ainda) a memória é determinística: o que ficou aberto e o que
foi decidido da última vez, tirado do banco. Depois da ata, a IA compara as duas pontas
e diz o que foi resolvido, o que segue aberto, o que mudou e o que apareceu de novo.
O resultado fica guardado com uma impressão digital das atas envolvidas: muda ata,
muda memória; senão, nada é recalculado.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.application.brief import Brief, BriefService, RelatedSession
from app.application.prompts import MEMORY_PROMPT, MEMORY_SYSTEM
from app.application.summarize import _extract_json, _string_list, _text, strip_stamps
from app.domain.models import Session, Summary, TaskItem
from app.domain.ports import LlmPort
from app.infrastructure.persistence.sqlite import SqliteStore

MAX_PREVIOUS = 3
MATCH_THRESHOLD = 0.6


@dataclass(frozen=True)
class ThreadEntry:
    session_id: str
    title: str
    started_at: datetime
    reason: str
    has_summary: bool
    decisions: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Resolved:
    item: str
    how: str
    task_id: str | None = None


@dataclass(frozen=True)
class Change:
    before: str
    now: str


@dataclass(frozen=True)
class Memory:
    session_id: str
    # "before": ainda sem ata (ou sem reuniões anteriores); "after": comparação feita pela IA.
    mode: str
    generated: bool
    thread: list[ThreadEntry] = field(default_factory=list)
    resolved: list[Resolved] = field(default_factory=list)
    still_open: list[str] = field(default_factory=list)
    changed: list[Change] = field(default_factory=list)
    new_items: list[str] = field(default_factory=list)
    watch: list[str] = field(default_factory=list)
    pending: list[TaskItem] = field(default_factory=list)
    language: str | None = None
    created_at: datetime | None = None
    # A ata atual mudou desde a última comparação: vale refazer.
    stale: bool = False


class MemoryService:
    def __init__(self, llm: LlmPort, store: SqliteStore, brief: BriefService | None = None) -> None:
        self._llm = llm
        self._store = store
        self._brief = brief or BriefService(store)

    async def recall(self, session_id: str) -> Memory:
        """O que já se sabe sem chamar a IA: fio, pendências e, se houver, a comparação guardada."""
        session, brief, summary = await self._load(session_id)
        thread = _thread(brief)
        pending = list(brief.pending)
        if not brief.related:
            return Memory(session_id=session_id, mode="before", generated=False, pending=pending)
        if summary is None:
            return Memory(
                session_id=session_id,
                mode="before",
                generated=False,
                thread=thread,
                still_open=_open_before(brief),
                watch=_watch_before(brief),
                pending=pending,
            )
        fingerprint = _fingerprint(summary, brief)
        cached = await self._store.get_memory(session_id)
        if cached is not None:
            saved_fingerprint, payload, created_at = cached
            memory = _from_payload(session_id, payload, thread, pending, created_at)
            return memory if saved_fingerprint == fingerprint else _replace_stale(memory)
        return Memory(
            session_id=session_id,
            mode="after",
            generated=False,
            thread=thread,
            still_open=_open_before(brief),
            pending=pending,
        )

    async def compare(self, session_id: str, *, force: bool = False) -> Memory:
        """Compara a ata atual com as anteriores (IA). Reaproveita o resultado quando nada mudou."""
        session, brief, summary = await self._load(session_id)
        thread = _thread(brief)
        pending = list(brief.pending)
        if not brief.related or summary is None:
            return await self.recall(session_id)
        fingerprint = _fingerprint(summary, brief)
        if not force:
            cached = await self._store.get_memory(session_id)
            if cached is not None and cached[0] == fingerprint:
                return _from_payload(session_id, cached[1], thread, pending, cached[2])
        raw = await self._llm.generate_json(
            MEMORY_PROMPT.format(previous=_render_previous(brief.related), current=_render_current(session, summary)),
            system=MEMORY_SYSTEM,
        )
        payload = parse_memory_json(raw, pending)
        now = datetime.now(tz=UTC)
        payload["created_at"] = now.isoformat()
        await self._store.save_memory(session_id, fingerprint, json.dumps(payload, ensure_ascii=False), now)
        return _from_payload(session_id, payload, thread, pending, now)

    async def prior_context(self, session: Session) -> str:
        """Bloco para o pedido da ata: decisões e pendências das reuniões anteriores da série."""
        brief = await self._brief.for_session(session.id)
        if not brief.related:
            return ""
        lines = [
            "Reuniões anteriores desta mesma série (mesmo título ou mesmas pessoas). Use só para reconhecer "
            "quando a conversa atual retoma algo: se uma pendência ou tarefa anterior foi resolvida ou decidida "
            "agora, diga isso explicitamente em \"decisions\" ou em \"topics\"; se seguiu em aberto e foi "
            "mencionada, mantenha em \"open_items\". Não copie nada daqui que a transcrição atual não mencione.",
        ]
        for item in brief.related[:MAX_PREVIOUS]:
            when = item.session.started_at.astimezone().strftime("%d/%m/%Y")
            lines.append(f"- {item.session.title} ({when})")
            for decision in item.decisions[:5]:
                lines.append(f"  decisão: {strip_stamps(decision)}")
            for open_item in item.open_items[:5]:
                lines.append(f"  pendência: {strip_stamps(open_item)}")
            for task in item.tasks[:5]:
                lines.append(f"  tarefa aberta: {task.text}" + (f" ({task.owner})" if task.owner else ""))
        return "\n".join(lines) + "\n\n"

    async def chat_context(self, session_id: str) -> str:
        """Bloco em inglês para o chat (o idioma do prompt do chat é o inglês)."""
        memory = await self.recall(session_id)
        if not memory.thread:
            return ""
        lines = ["Earlier meetings in the same series (most recent first):"]
        for entry in memory.thread:
            when = entry.started_at.astimezone().strftime("%Y-%m-%d")
            lines.append(f"- {entry.title} ({when})")
            for decision in entry.decisions[:4]:
                lines.append(f"  decided: {strip_stamps(decision)}")
            for open_item in entry.open_items[:4]:
                lines.append(f"  open: {strip_stamps(open_item)}")
        if memory.generated:
            if memory.resolved:
                lines.append("Resolved in the focused meeting: " + " | ".join(f"{r.item} — {r.how}" for r in memory.resolved[:6]))
            if memory.still_open:
                lines.append("Still open after it: " + " | ".join(memory.still_open[:6]))
            if memory.changed:
                lines.append("Changed decisions: " + " | ".join(f"{c.before} → {c.now}" for c in memory.changed[:4]))
            if memory.new_items:
                lines.append("New this time: " + " | ".join(memory.new_items[:6]))
        elif memory.pending:
            lines.append("Tasks still pending from those meetings: " + " | ".join(t.text for t in memory.pending[:8]))
        return "\n".join(lines)

    async def _load(self, session_id: str) -> tuple[Session, Brief, Summary | None]:
        session = await self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        brief = await self._brief.for_session(session_id)
        summary = await self._store.get_summary(session_id)
        return session, brief, summary


# ----------------------------------------------------------------- montagem


def _thread(brief: Brief) -> list[ThreadEntry]:
    return [
        ThreadEntry(
            session_id=item.session.id,
            title=item.session.title,
            started_at=item.session.started_at,
            reason=item.reason,
            has_summary=bool(item.overview or item.decisions or item.open_items),
            decisions=list(item.decisions),
            open_items=list(item.open_items),
        )
        for item in brief.related
    ]


def _open_before(brief: Brief) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in brief.related:
        for text in item.open_items:
            key = _norm(text)
            if key and key not in seen:
                seen.add(key)
                out.append(strip_stamps(text))
    return out[:10]


def _watch_before(brief: Brief) -> list[str]:
    latest = brief.related[0] if brief.related else None
    if latest is None:
        return []
    return [strip_stamps(item) for item in latest.decisions[:4]]


def _fingerprint(summary: Summary, brief: Brief) -> str:
    digest = hashlib.sha1()
    digest.update(summary.id.encode())
    for item in brief.related:
        digest.update(item.session.id.encode())
        digest.update(item.overview[:60].encode("utf-8", "ignore"))
        digest.update(str(len(item.decisions) + len(item.open_items)).encode())
    for task in sorted(brief.pending, key=lambda item: item.id):
        digest.update(f"{task.id}:{int(task.done)}".encode())
    return digest.hexdigest()


def _render_previous(related: list[RelatedSession]) -> str:
    blocks: list[str] = []
    for item in related[:MAX_PREVIOUS]:
        when = item.session.started_at.astimezone().strftime("%d/%m/%Y")
        lines = [f"## {item.session.title} ({when})"]
        if item.overview:
            lines.append(f"Resumo: {item.overview}")
        if item.decisions:
            lines.append("Decisões:")
            lines.extend(f"- {strip_stamps(text)}" for text in item.decisions[:8])
        if item.open_items:
            lines.append("Pendências:")
            lines.extend(f"- {strip_stamps(text)}" for text in item.open_items[:8])
        if item.tasks:
            lines.append("Tarefas ainda abertas:")
            lines.extend(f"- {task.text}" + (f" ({task.owner})" if task.owner else "") for task in item.tasks[:8])
        if len(lines) == 1:
            lines.append("(sem ata)")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_current(session: Session, summary: Summary) -> str:
    when = session.started_at.astimezone().strftime("%d/%m/%Y")
    lines = [f"## {session.title} ({when})"]
    if summary.overview:
        lines.append(f"Resumo: {summary.overview}")
    for topic in summary.topics[:8]:
        if topic.points:
            lines.append(f"{topic.title}:")
            lines.extend(f"- {strip_stamps(point)}" for point in topic.points[:6])
    if summary.decisions:
        lines.append("Decisões:")
        lines.extend(f"- {strip_stamps(text)}" for text in summary.decisions)
    if summary.action_items:
        lines.append("Ações:")
        lines.extend(f"- {strip_stamps(item.text)}" + (f" ({item.owner})" if item.owner else "") for item in summary.action_items)
    if summary.open_items:
        lines.append("Pendências:")
        lines.extend(f"- {strip_stamps(text)}" for text in summary.open_items)
    return "\n".join(lines)


def parse_memory_json(raw: str, pending: list[TaskItem]) -> dict:
    payload = _extract_json(raw)
    resolved: list[dict] = []
    for item in payload.get("resolved") or []:
        if isinstance(item, str) and item.strip():
            resolved.append({"item": item.strip(), "how": "", "task_id": match_task(item, pending)})
        elif isinstance(item, dict):
            text = str(item.get("item") or "").strip()
            if text:
                resolved.append({"item": text, "how": _text(item.get("how")), "task_id": match_task(text, pending)})
    changed: list[dict] = []
    for item in payload.get("changed") or []:
        if isinstance(item, dict):
            before = str(item.get("before") or "").strip()
            now = str(item.get("now") or "").strip()
            if before and now:
                changed.append({"before": before, "now": now})
    language = payload.get("language")
    still_open = _string_list(payload.get("still_open"))[:12]
    # Modelos pequenos repetem a mesma frase em "novo" e em "segue aberto"; novo é só o que não estava em lugar nenhum.
    taken = {_norm(item) for item in still_open} | {_norm(item["item"]) for item in resolved}
    new_items = [item for item in _string_list(payload.get("new_items")) if _norm(item) not in taken]
    return {
        "language": str(language).strip().lower()[:5] if language else None,
        "resolved": resolved[:12],
        "still_open": still_open,
        "changed": changed[:8],
        "new_items": new_items[:8],
        "watch": _string_list(payload.get("watch"))[:6],
    }


def match_task(text: str, pending: list[TaskItem]) -> str | None:
    """Pendência resolvida → tarefa aberta da central com o mesmo texto (ou quase)."""
    wanted = _norm(text)
    if not wanted:
        return None
    best: tuple[float, str] | None = None
    for task in pending:
        candidate = _norm(task.text)
        if not candidate:
            continue
        if candidate == wanted or candidate in wanted or wanted in candidate:
            score = 1.0
        else:
            a, b = set(wanted.split()), set(candidate.split())
            score = len(a & b) / len(a | b) if a and b else 0.0
        if score >= MATCH_THRESHOLD and (best is None or score > best[0]):
            best = (score, task.id)
    return best[1] if best else None


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", strip_stamps(text).casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\W+", " ", folded).strip()


def _from_payload(
    session_id: str,
    payload: dict | str,
    thread: list[ThreadEntry],
    pending: list[TaskItem],
    created_at: datetime | None,
) -> Memory:
    data = json.loads(payload) if isinstance(payload, str) else payload
    pending_ids = {task.id for task in pending}
    resolved = [
        Resolved(
            item=str(item.get("item") or ""),
            how=str(item.get("how") or ""),
            task_id=item.get("task_id") if item.get("task_id") in pending_ids else None,
        )
        for item in data.get("resolved") or []
        if isinstance(item, dict) and item.get("item")
    ]
    changed = [
        Change(before=str(item.get("before") or ""), now=str(item.get("now") or ""))
        for item in data.get("changed") or []
        if isinstance(item, dict)
    ]
    return Memory(
        session_id=session_id,
        mode="after",
        generated=True,
        thread=thread,
        resolved=resolved,
        still_open=[str(item) for item in data.get("still_open") or []],
        changed=changed,
        new_items=[str(item) for item in data.get("new_items") or []],
        watch=[str(item) for item in data.get("watch") or []],
        pending=pending,
        language=data.get("language"),
        created_at=created_at,
    )


def _replace_stale(memory: Memory) -> Memory:
    from dataclasses import replace

    return replace(memory, stale=True)
