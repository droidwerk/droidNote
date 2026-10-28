from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.v1.deps import get_container
from app.application.tasks import TaskService
from app.core.security import verify_token
from app.domain.models import TaskItem
from app.schemas.api import TaskIn, TaskOut, TaskUpdateIn

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(verify_token)])


def _service(request: Request) -> TaskService:
    container = get_container(request.app)
    return container.tasks or TaskService(container.store)


async def to_out(request: Request, items: list[TaskItem]) -> list[TaskOut]:
    store = get_container(request.app).store
    sessions = {item.id: item for item in await store.list_sessions()}
    return [TaskOut.from_domain(item, sessions.get(item.session_id or "")) for item in items]


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    request: Request,
    status_filter: str = Query(default="all", alias="status", pattern="^(open|done|all)$"),
    session_id: str | None = Query(default=None),
) -> list[TaskOut]:
    return await to_out(request, await _service(request).list(status_filter, session_id))


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskIn, request: Request) -> TaskOut:
    if payload.session_id and await get_container(request.app).store.get_session(payload.session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session")
    try:
        task = await _service(request).create(
            payload.text, owner=payload.owner, due=payload.due, session_id=payload.session_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await get_container(request.app).bus.publish({"type": "tasks"})
    return (await to_out(request, [task]))[0]


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, payload: TaskUpdateIn, request: Request) -> TaskOut:
    try:
        task = await _service(request).update(
            task_id,
            text=payload.text,
            owner=payload.owner,
            due=payload.due,
            done=payload.done,
            fields=set(payload.model_fields_set),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task") from exc
    await get_container(request.app).bus.publish({"type": "tasks"})
    return (await to_out(request, [task]))[0]


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, request: Request) -> None:
    try:
        await _service(request).delete(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task") from exc
    await get_container(request.app).bus.publish({"type": "tasks"})
