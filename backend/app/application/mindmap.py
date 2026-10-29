"""Mapa mental da conversa.

Nasce da ata, sem IA e sem custo: assuntos → pontos, decisões, ações, pendências, material de
apoio e, quando existe, o que mudou desde a reunião anterior. Cada folha guarda o momento da
fala (clicar leva à transcrição) e, nas ações, a tarefa da central. A pessoa edita o mapa à
vontade; a edição é dela e não é refeita sozinha. "Reorganizar com IA" reagrupa os ramos
preservando as folhas e seus momentos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.application.prompts import MINDMAP_PROMPT, MINDMAP_SYSTEM
from app.application.summarize import _STAMP, _extract_json, strip_stamps
from app.domain.models import Session, Summary, TaskItem
from app.domain.ports import LlmPort
from app.infrastructure.persistence.sqlite import SqliteStore

MAX_REFINE_NODES = 120
# Ramos fixos, por idioma da ata (a interface traduz o resto; estes nomes ficam no mapa salvo).
BRANCHES = {
    "pt": {"decisions": "Decisões", "actions": "Ações", "open": "Pendências", "material": "Material", "since": "Desde a última vez"},
    "en": {"decisions": "Decisions", "actions": "Actions", "open": "Open items", "material": "Material", "since": "Since last time"},
    "es": {"decisions": "Decisiones", "actions": "Acciones", "open": "Pendientes", "material": "Material", "since": "Desde la última vez"},
    "it": {"decisions": "Decisioni", "actions": "Azioni", "open": "In sospeso", "material": "Materiale", "since": "Dall'ultima volta"},
    "de": {"decisions": "Entscheidungen", "actions": "Aufgaben", "open": "Offen", "material": "Material", "since": "Seit dem letzten Mal"},
    "fr": {"decisions": "Décisions", "actions": "Actions", "open": "En suspens", "material": "Documents", "since": "Depuis la dernière fois"},
    "ru": {"decisions": "Решения", "actions": "Задачи", "open": "Открытые вопросы", "material": "Материалы", "since": "С прошлого раза"},
}
ICONS = {"decision": "✔", "task": "☐", "task_done": "☑", "open": "❓", "document": "📎", "resolved": "✔", "changed": "↻", "new": "✦"}


@dataclass(frozen=True)
class MindMapRecord:
    session_id: str
    origin: str  # auto | edited | ai
    summary_id: str | None
    data: dict[str, Any]
    updated_at: datetime


class MindMapService:
    def __init__(self, store: SqliteStore, llm: LlmPort | None = None, memory: Any = None) -> None:
        self._store = store
        self._llm = llm
        self._memory = memory

    async def get(self, session_id: str) -> MindMapRecord:
        """O mapa guardado, se a pessoa editou ou se a ata não mudou; senão, um novo a partir da ata."""
        session = await self._require(session_id)
        summary = await self._store.get_summary(session_id)
        saved = await self._store.get_mindmap(session_id)
        current_summary_id = summary.id if summary else None
        if saved is not None and (saved.origin != "auto" or saved.summary_id == current_summary_id):
            return saved
        return await self._rebuild(session, summary)

    async def reset(self, session_id: str) -> MindMapRecord:
        session = await self._require(session_id)
        summary = await self._store.get_summary(session_id)
        return await self._rebuild(session, summary)

    async def save(self, session_id: str, data: dict[str, Any]) -> MindMapRecord:
        await self._require(session_id)
        summary = await self._store.get_summary(session_id)
        record = MindMapRecord(
            session_id=session_id,
            origin="edited",
            summary_id=summary.id if summary else None,
            data=_sanitize(data),
            updated_at=datetime.now(tz=UTC),
        )
        await self._store.save_mindmap(record)
        return record

    async def refine(self, session_id: str) -> MindMapRecord:
        """A IA reagrupa os ramos; as folhas (com momento e tarefa) são preservadas pelo id."""
        if self._llm is None:
            raise RuntimeError("llm")
        session = await self._require(session_id)
        current = await self.get(session_id)
        root = current.data.get("nodeData") or {}
        index: dict[str, dict[str, Any]] = {}
        outline = _outline(root, index)
        raw = await self._llm.generate_json(
            MINDMAP_PROMPT.format(title=session.title, outline=outline), system=MINDMAP_SYSTEM
        )
        payload = _extract_json(raw)
        tree = payload.get("root") if isinstance(payload, dict) else None
        if not isinstance(tree, dict) or not tree.get("children"):
            raise RuntimeError("invalid")
        counter = [0]
        new_root = _rebuild_from_ai(tree, index, counter)
        new_root["id"] = "root"
        new_root["topic"] = session.title
        _restore_missing_leaves(new_root, index)
        summary = await self._store.get_summary(session_id)
        record = MindMapRecord(
            session_id=session_id,
            origin="ai",
            summary_id=summary.id if summary else None,
            data={"nodeData": new_root, "direction": current.data.get("direction", 2)},
            updated_at=datetime.now(tz=UTC),
        )
        await self._store.save_mindmap(record)
        return record

    async def _rebuild(self, session: Session, summary: Summary | None) -> MindMapRecord:
        tasks = await self._store.list_tasks(session_id=session.id)
        lister = getattr(self._store, "list_documents", None)
        documents = await lister(session_id=session.id) if callable(lister) else []
        since = await self._since_last_time(session.id)
        data = build_map(session, summary, tasks, [item.name for item in documents], since)
        record = MindMapRecord(
            session_id=session.id,
            origin="auto",
            summary_id=summary.id if summary else None,
            data=data,
            updated_at=datetime.now(tz=UTC),
        )
        await self._store.save_mindmap(record)
        return record

    async def _since_last_time(self, session_id: str) -> dict[str, list[str]] | None:
        if self._memory is None:
            return None
        try:
            memory = await self._memory.recall(session_id)
        except Exception:
            return None
        if not memory.generated:
            return None
        return {
            "resolved": [item.item for item in memory.resolved],
            "changed": [f"{item.before} → {item.now}" for item in memory.changed],
            "new": list(memory.new_items),
        }

    async def _require(self, session_id: str) -> Session:
        session = await self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session


# ------------------------------------------------------------------ construção


def build_map(
    session: Session,
    summary: Summary | None,
    tasks: list[TaskItem],
    documents: list[str],
    since: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    language = ((summary.language if summary else None) or session.language or "pt")[:2].lower()
    names = BRANCHES.get(language, BRANCHES["pt"])
    counter = [0]

    def node(topic: str, kind: str, **meta: Any) -> dict[str, Any]:
        counter[0] += 1
        clean, at_ms = split_stamp(topic)
        item: dict[str, Any] = {"id": f"n{counter[0]}", "topic": clean or topic, "metadata": {"kind": kind}}
        if at_ms is not None:
            item["metadata"]["at_ms"] = at_ms
            item["tags"] = [_clock(at_ms)]
        for key, value in meta.items():
            if value is not None:
                item["metadata"][key] = value
        icon = ICONS.get("task_done" if kind == "task" and meta.get("done") else kind)
        if icon:
            item["icons"] = [icon]
        return item

    root: dict[str, Any] = {"id": "root", "topic": session.title, "metadata": {"kind": "root"}, "children": []}
    if summary is not None:
        for topic in summary.topics:
            branch = node(topic.title, "topic")
            branch["children"] = [node(point, "point") for point in topic.points]
            root["children"].append(branch)
        if summary.decisions:
            branch = node(names["decisions"], "decisions")
            branch["children"] = [node(text, "decision") for text in summary.decisions]
            root["children"].append(branch)
    task_nodes = []
    for task in tasks:
        label = task.text + (f" — {task.owner}" if task.owner else "")
        task_nodes.append(node(label, "task", task_id=task.id, done=task.done))
    if not task_nodes and summary is not None:
        for item in summary.action_items:
            label = item.text + (f" — {item.owner}" if item.owner else "")
            task_nodes.append(node(label, "task"))
    if task_nodes:
        branch = node(names["actions"], "actions")
        branch["children"] = task_nodes
        root["children"].append(branch)
    if summary is not None and summary.open_items:
        branch = node(names["open"], "open_items")
        branch["children"] = [node(text, "open") for text in summary.open_items]
        root["children"].append(branch)
    if documents:
        branch = node(names["material"], "material")
        branch["children"] = [node(name, "document") for name in documents]
        root["children"].append(branch)
    if since and any(since.values()):
        branch = node(names["since"], "since")
        branch["children"] = (
            [node(text, "resolved") for text in since.get("resolved", [])]
            + [node(text, "changed") for text in since.get("changed", [])]
            + [node(text, "new") for text in since.get("new", [])]
        )
        root["children"].append(branch)
    return {"nodeData": root, "direction": 2}


def split_stamp(text: str) -> tuple[str, int | None]:
    """"Fechar o piloto (12:40)" → ("Fechar o piloto", 760000)."""
    match = None
    for match in _STAMP.finditer(text):
        pass
    if match is None:
        return text.strip(), None
    parts = [int(part) for part in match.group(1).split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        hours, (minutes, seconds) = 0, parts
    return strip_stamps(text), (hours * 3600 + minutes * 60 + seconds) * 1000


def _clock(ms: int) -> str:
    total = max(0, ms) // 1000
    return f"{total // 60:02d}:{total % 60:02d}"


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """Só o que o mapa precisa, sem o `parent` circular que o editor acrescenta."""
    root = data.get("nodeData") if isinstance(data, dict) else None
    if not isinstance(root, dict):
        raise ValueError("nodeData")

    def clean(item: dict[str, Any], depth: int) -> dict[str, Any]:
        out: dict[str, Any] = {"id": str(item.get("id") or ""), "topic": str(item.get("topic") or "")[:300]}
        for key in ("tags", "icons", "expanded", "direction", "style", "metadata", "note", "hyperLink", "branchColor"):
            if key in item and item[key] is not None:
                out[key] = item[key]
        children = item.get("children")
        if isinstance(children, list) and depth < 12:
            out["children"] = [clean(child, depth + 1) for child in children if isinstance(child, dict)]
        return out

    out: dict[str, Any] = {"nodeData": clean(root, 0)}
    if isinstance(data.get("direction"), int):
        out["direction"] = data["direction"]
    return out


# ---------------------------------------------------------- reorganizar com IA


def _outline(node: dict[str, Any], index: dict[str, dict[str, Any]], depth: int = 0) -> str:
    lines: list[str] = []
    if depth > 0:
        index[str(node.get("id"))] = node
        lines.append("  " * (depth - 1) + f"- [{node.get('id')}] {node.get('topic', '')}")
    for child in node.get("children") or []:
        if isinstance(child, dict):
            lines.append(_outline(child, index, depth + 1))
    return "\n".join(line for line in lines if line)


def _rebuild_from_ai(item: dict[str, Any], index: dict[str, dict[str, Any]], counter: list[int]) -> dict[str, Any]:
    ref = str(item.get("ref") or "").strip()
    topic = str(item.get("topic") or "").strip()
    source = index.get(ref)
    if source is not None:
        out = {key: value for key, value in source.items() if key not in {"children", "parent"}}
        if topic:
            out["topic"] = topic[:300]
    else:
        counter[0] += 1
        out = {"id": f"ai{counter[0]}", "topic": topic[:300] or "…", "metadata": {"kind": "ai"}}
    children = item.get("children")
    if isinstance(children, list) and counter[0] < MAX_REFINE_NODES:
        out["children"] = [_rebuild_from_ai(child, index, counter) for child in children if isinstance(child, dict)]
    return out


def _restore_missing_leaves(root: dict[str, Any], index: dict[str, dict[str, Any]]) -> None:
    """Folha com momento ou tarefa que a IA esqueceu volta para o fim do mapa: nada se perde."""
    used: set[str] = set()

    def walk(node: dict[str, Any]) -> None:
        used.add(str(node.get("id")))
        for child in node.get("children") or []:
            walk(child)

    walk(root)
    lost = [
        {key: value for key, value in node.items() if key not in {"children", "parent"}}
        for node_id, node in index.items()
        if node_id not in used
        and isinstance(node.get("metadata"), dict)
        and (node["metadata"].get("at_ms") is not None or node["metadata"].get("task_id"))
    ]
    if lost:
        root.setdefault("children", []).append({"id": "ai_lost", "topic": "…", "metadata": {"kind": "ai"}, "children": lost})


def to_markdown(data: dict[str, Any]) -> str:
    """Esboço em Markdown (para copiar ou exportar)."""
    root = data.get("nodeData") or {}
    lines = [f"# {root.get('topic', '')}"]

    def walk(node: dict[str, Any], depth: int) -> None:
        for child in node.get("children") or []:
            stamp = ""
            meta = child.get("metadata") or {}
            if isinstance(meta, dict) and meta.get("at_ms") is not None:
                stamp = f" ({_clock(int(meta['at_ms']))})"
            lines.append("  " * depth + f"- {child.get('topic', '')}{stamp}")
            walk(child, depth + 1)

    walk(root, 0)
    return "\n".join(lines) + "\n"


def loads(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


_ = re  # mantido para quem importar helpers deste módulo
