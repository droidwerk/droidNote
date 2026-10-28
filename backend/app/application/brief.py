"""Contexto: antes de uma reunião, o que ficou pendente e o que foi decidido da última vez.

Reunião "parecida" é a que tem o mesmo título (sem datas, horas e nome do app)
ou as mesmas pessoas. Tudo vem do banco local; o calendário ICS só diz o que vem aí.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.models import Session, TaskItem
from app.infrastructure.calendar.ics import CalendarError, CalendarEvent, IcsCalendar
from app.infrastructure.persistence.sqlite import SqliteStore

CALENDAR_KEY = "calendar_ics_url"
TITLE_MATCH = 0.5
MAX_RELATED = 3

# Palavras que aparecem em quase todo título e não dizem de que reunião se trata.
GENERIC = {
    "reuniao", "meeting", "call", "chamada", "sync", "weekly", "semanal",
    "zoom", "teams", "microsoft", "meet", "google", "slack", "discord", "whatsapp",
    "webex", "skype", "telegram", "navegador", "browser", "chrome", "edge", "firefox",
    "gravacao", "recording", "ditado", "dictation", "aula", "lecture", "nova", "new",
    "de", "da", "do", "das", "dos", "com", "e", "a", "o", "the", "with", "and", "for",
    "para", "por", "em", "on", "of", "y", "con", "und", "mit", "et", "avec", "di", "per",
}


@dataclass(frozen=True)
class RelatedSession:
    session: Session
    score: float
    reason: str
    overview: str = ""
    decisions: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    tasks: list[TaskItem] = field(default_factory=list)


@dataclass(frozen=True)
class Brief:
    title: str
    people: list[str]
    related: list[RelatedSession]
    pending: list[TaskItem]


def title_tokens(title: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", title.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"\d{1,2}[/.-]\d{1,2}([/.-]\d{2,4})?", " ", folded)
    folded = re.sub(r"\d{1,2}[:h]\d{2}", " ", folded)
    words = re.findall(r"[a-zЀ-ӿ][a-z0-9Ѐ-ӿ]+", folded)
    return {word for word in words if word not in GENERIC and len(word) > 1}


def title_similarity(left: str, right: str) -> float:
    a, b = title_tokens(left), title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _person_key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch)).strip()


def match_people(names: Iterable[str], known: dict[str, str]) -> set[str]:
    """Nomes do convite → ids de pessoas cadastradas (nome inteiro ou primeiro nome único)."""
    by_full = {_person_key(name): pid for pid, name in known.items()}
    firsts: dict[str, list[str]] = {}
    for pid, name in known.items():
        first = _person_key(name).split(" ")[0]
        firsts.setdefault(first, []).append(pid)
    found: set[str] = set()
    for raw in names:
        key = _person_key(raw)
        if not key:
            continue
        if key in by_full:
            found.add(by_full[key])
            continue
        first = re.split(r"[ ._]", key)[0]
        if len(firsts.get(first, [])) == 1:
            found.add(firsts[first][0])
    return found


class BriefService:
    def __init__(self, store: SqliteStore, calendar: IcsCalendar | None = None) -> None:
        self._store = store
        self._calendar = calendar or IcsCalendar()

    async def for_session(self, session_id: str) -> Brief:
        session = await self._store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        people = await self._store.list_session_participants(session_id)
        return await self.build(
            session.title,
            person_ids={item.id for item in people},
            exclude=session_id,
            before=session.started_at,
        )

    async def for_title(self, title: str, people: Sequence[str] = ()) -> Brief:
        known = {item.id: item.name for item in await self._store.list_people()}
        self_id = await self._store.get_setting("self_person_id") or ""
        guests = [name for name in people if not (self_id and match_people([name], known) == {self_id})]
        return await self.build(
            title,
            person_ids=match_people(guests, known),
            people=list(people),
            group_size=len(guests),
        )

    async def build(
        self,
        title: str,
        *,
        person_ids: set[str],
        people: list[str] | None = None,
        exclude: str | None = None,
        before: datetime | None = None,
        group_size: int | None = None,
    ) -> Brief:
        self_id = await self._store.get_setting("self_person_id") or ""
        wanted = {pid for pid in person_ids if pid != self_id}
        # 1:1 vale pelo tamanho do convite, não só por quem está cadastrado.
        size = len(wanted) if group_size is None else group_size
        names = {item.id: item.name for item in await self._store.list_people()}
        candidates: list[tuple[float, str, Session]] = []
        for session in await self._store.list_sessions():
            if session.id == exclude or session.status == "recording":
                continue
            if before is not None and session.started_at >= before:
                continue
            similarity = title_similarity(title, session.title)
            overlap = 0
            if wanted:
                theirs = {item.id for item in await self._store.list_session_participants(session.id)}
                overlap = len(wanted & (theirs - {self_id}))
            by_title = similarity >= TITLE_MATCH
            by_people = overlap >= 2 or (overlap >= 1 and size == 1)
            if not (by_title or by_people):
                continue
            reason = "both" if by_title and by_people else "title" if by_title else "people"
            candidates.append((similarity + 0.25 * min(overlap, 3), reason, session))
        # Entre as parecidas, a mais recente conta mais que a mais parecida; mas uma
        # gravação sem ata nem tarefas não diz nada e vai para o fim da fila.
        candidates.sort(key=lambda item: item[2].started_at, reverse=True)
        loaded = []
        for score, reason, session in candidates:
            summary = await self._store.get_summary(session.id)
            tasks = await self._store.list_tasks(session_id=session.id)
            loaded.append((score, reason, session, summary, tasks))
        loaded.sort(key=lambda item: item[3] is None and not item[4])
        related: list[RelatedSession] = []
        pending: dict[str, TaskItem] = {}
        for score, reason, session, summary, tasks in loaded[:MAX_RELATED]:
            open_tasks = [task for task in tasks if not task.done]
            for task in open_tasks:
                pending.setdefault(task.id, task)
            related.append(
                RelatedSession(
                    session=session,
                    score=round(score, 3),
                    reason=reason,
                    overview=summary.overview if summary else "",
                    decisions=list(summary.decisions[:6]) if summary else [],
                    open_items=list(summary.open_items[:6]) if summary else [],
                    tasks=open_tasks,
                )
            )
        shown_people = people if people is not None else [names[pid] for pid in wanted if pid in names]
        return Brief(title=title, people=shown_people, related=related, pending=list(pending.values()))

    async def calendar_url(self) -> str:
        return (await self._store.get_setting(CALENDAR_KEY)) or ""

    async def upcoming(
        self, *, hours: float = 36, now: datetime | None = None
    ) -> tuple[bool, str | None, list[tuple[CalendarEvent, Brief]]]:
        url = await self.calendar_url()
        if not url:
            return False, None, []
        try:
            events = await self._calendar.upcoming(url, now=now or datetime.now(tz=UTC), hours=hours)
        except CalendarError as exc:
            return True, str(exc), []
        out: list[tuple[CalendarEvent, Brief]] = []
        for event in events[:8]:
            brief = await self.for_title(event.title, [item.name for item in event.attendees])
            out.append((event, brief))
        return True, None, out

    async def test(self, url: str) -> int:
        events = await self._calendar.upcoming(url, hours=24 * 14)
        return len(events)
