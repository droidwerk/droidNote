"""Central de tarefas: as ações de todas as atas numa lista só.

Cada ata gerada sincroniza as tarefas "ai" da sua sessão. Gerar a ata de novo
não perde o que a pessoa já marcou: a tarefa com o mesmo texto mantém o id e o
"feito"; as abertas que sumiram da ata nova saem; as feitas ficam como histórico.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.models import ActionItem, TaskItem
from app.infrastructure.persistence.sqlite import SqliteStore, new_id

BACKFILL_KEY = "tasks_backfilled"


class TaskService:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    async def list(self, status: str = "all", session_id: str | None = None) -> list[TaskItem]:
        items = await self._store.list_tasks(session_id=session_id)
        if status == "open":
            return [item for item in items if not item.done]
        if status == "done":
            return [item for item in items if item.done]
        return items

    async def create(
        self,
        text: str,
        *,
        owner: str | None = None,
        due: str | None = None,
        session_id: str | None = None,
    ) -> TaskItem:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("empty")
        task = TaskItem(
            id=new_id(),
            text=cleaned,
            owner=_clean(owner),
            due=_clean(due),
            session_id=session_id or None,
            origin="manual",
            created_at=datetime.now(tz=UTC),
        )
        return await self._store.save_task(task)

    async def update(
        self,
        task_id: str,
        *,
        text: str | None = None,
        owner: str | None = None,
        due: str | None = None,
        done: bool | None = None,
        fields: set[str] | None = None,
    ) -> TaskItem:
        task = await self._store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        given = fields or set()
        if text is not None and text.strip():
            task = replace(task, text=text.strip())
        if "owner" in given:
            task = replace(task, owner=_clean(owner))
        if "due" in given:
            task = replace(task, due=_clean(due))
        if done is not None and done != task.done:
            task = replace(task, done=done, done_at=datetime.now(tz=UTC) if done else None)
        return await self._store.save_task(task)

    async def delete(self, task_id: str) -> None:
        if not await self._store.delete_task(task_id):
            raise KeyError(task_id)

    async def sync_from_summary(self, session_id: str, items: list[ActionItem]) -> list[TaskItem]:
        existing = [item for item in await self._store.list_tasks(session_id=session_id) if item.origin == "ai"]
        by_key: dict[str, TaskItem] = {}
        for item in existing:
            by_key.setdefault(task_key(item.text), item)
        kept: set[str] = set()
        now = datetime.now(tz=UTC)
        for action in items:
            text = action.text.strip()
            if not text:
                continue
            key = task_key(text)
            match = by_key.get(key)
            if match is not None and match.id not in kept:
                task = replace(match, text=text, owner=_clean(action.owner), due=_clean(action.due))
            else:
                task = TaskItem(
                    id=new_id(),
                    session_id=session_id,
                    text=text,
                    owner=_clean(action.owner),
                    due=_clean(action.due),
                    origin="ai",
                    created_at=now,
                )
            kept.add(task.id)
            await self._store.save_task(task)
        for item in existing:
            if item.id not in kept and not item.done:
                await self._store.delete_task(item.id)
        return await self._store.list_tasks(session_id=session_id)

    async def backfill(self) -> int:
        """Primeira execução com a central: traz as ações das atas que já existiam."""
        if (await self._store.get_setting(BACKFILL_KEY)) == "1":
            return 0
        count = 0
        for session_id in await self._store.sessions_with_summary():
            summary = await self._store.get_summary(session_id)
            if summary is None or not summary.action_items:
                continue
            await self.sync_from_summary(session_id, summary.action_items)
            count += 1
        await self._store.set_setting(BACKFILL_KEY, "1")
        return count


def task_key(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9а-яё]+", " ", folded).strip()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
