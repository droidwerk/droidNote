from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.v1.deps import get_container
from app.application.brief import Brief, BriefService
from app.core.security import verify_token
from app.infrastructure.calendar.ics import CalendarError
from app.schemas.api import (
    BriefOut,
    BriefSessionOut,
    CalendarEventOut,
    CalendarTestIn,
    CalendarTestOut,
    TaskOut,
    UpcomingOut,
)

router = APIRouter(tags=["brief"], dependencies=[Depends(verify_token)])


def _service(request: Request) -> BriefService:
    container = get_container(request.app)
    if container.brief is None:
        container.brief = BriefService(container.store)
    return container.brief


def brief_out(brief: Brief) -> BriefOut:
    titles = {item.session.id: item.session for item in brief.related}
    return BriefOut(
        title=brief.title,
        people=brief.people,
        related=[
            BriefSessionOut(
                session_id=item.session.id,
                title=item.session.title,
                started_at=item.session.started_at,
                reason=item.reason,  # type: ignore[arg-type]
                overview=item.overview,
                decisions=item.decisions,
                open_items=item.open_items,
                tasks=[TaskOut.from_domain(task, item.session) for task in item.tasks],
            )
            for item in brief.related
        ],
        pending=[TaskOut.from_domain(task, titles.get(task.session_id or "")) for task in brief.pending],
    )


@router.get("/brief", response_model=BriefOut)
async def get_brief(
    request: Request,
    session_id: str | None = Query(default=None),
    title: str | None = Query(default=None, max_length=300),
    people: str | None = Query(default=None, max_length=2000),
) -> BriefOut:
    service = _service(request)
    if session_id:
        try:
            return brief_out(await service.for_session(session_id))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session") from exc
    names = [item.strip() for item in (people or "").split(",") if item.strip()]
    return brief_out(await service.for_title(title or "", names))


@router.get("/calendar/upcoming", response_model=UpcomingOut)
async def upcoming(request: Request, hours: float = Query(default=36, ge=1, le=24 * 14)) -> UpcomingOut:
    configured, error, items = await _service(request).upcoming(hours=hours)
    return UpcomingOut(
        configured=configured,
        error=error,
        events=[
            CalendarEventOut(
                uid=event.uid,
                title=event.title,
                start=event.start,
                end=event.end,
                location=event.location,
                attendees=[item.name for item in event.attendees],
                brief=brief_out(brief),
            )
            for event, brief in items
        ],
    )


@router.post("/calendar/test", response_model=CalendarTestOut)
async def test_calendar(payload: CalendarTestIn, request: Request) -> CalendarTestOut:
    try:
        count = await _service(request).test(payload.url)
    except CalendarError as exc:
        return CalendarTestOut(ok=False, error=str(exc))
    return CalendarTestOut(ok=True, events=count)
