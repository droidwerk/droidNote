"""Grava sozinho quando uma reunião da agenda (ICS) começa.

Setting `calendar_auto_record` ("1"/"0"): ligado ao conectar a agenda pela primeira vez.
Quem já tinha agenda antes desta versão fica desligado e recebe a oferta uma vez
(`migrate_auto_record`). Agenda só com livre/ocupado e evento sem título não gravam
sozinhos: o bloco "Ocupado" pode ser consulta médica ou assunto pessoal. Exceção:
`calendar_record_busy` = "1" (padrão desligado, só o usuário liga) grava esses blocos
com o título padrão da gravação ("Reunião <data> <hora>", capture._default_title).
A gravação nasce com o fim do evento (planned_end): na hora marcada o
CaptureService pergunta se continua e, sem resposta e sem fala, encerra.
Independe da detecção de reunião pelo microfone (MEETING_DETECTION_ENABLED).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta

from app.application.bus import EventBus
from app.application.brief import CALENDAR_KEY, busy_only
from app.core.logging import get_logger
from app.domain.ports import SessionRepository
from app.infrastructure.calendar.ics import CalendarError, CalendarEvent, IcsCalendar

log = get_logger("calendar_watch")

SETTING_KEY = "calendar_auto_record"
OFFER_KEY = "calendar_auto_record_offer"
BUSY_KEY = "calendar_record_busy"
TICK_S = 30.0
REFRESH_S = 300.0
LOOKAHEAD_HOURS = 24 * 7
EARLY = timedelta(seconds=30)
LATE = timedelta(minutes=10)
# Evento de dia inteiro já fica fora do ics.py; isto pega bloco "ocupado o dia todo" com hora.
MAX_LENGTH = timedelta(hours=20)


class CalendarRecorder:
    def __init__(
        self,
        store: SessionRepository,
        calendar: IcsCalendar,
        bus: EventBus,
        *,
        is_recording: Callable[[], bool],
        asr_ready: Callable[[], bool],
        start_capture: Callable[[str, datetime], Awaitable[str | None]],
        live_span: Callable[[], tuple[datetime | None, datetime | None]] = lambda: (None, None),
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._store = store
        self._calendar = calendar
        self._bus = bus
        self._is_recording = is_recording
        self._asr_ready = asr_ready
        self._start_capture = start_capture
        self._live_span = live_span
        self._clock = clock
        self._wall = wall
        # ponytail: cresce um item por reunião gravada; some ao reiniciar o app.
        self._fired: set[str] = set()
        self._events: list[CalendarEvent] = []
        self._fetched_at: float | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                events = await self._load()
                if events:
                    await self.tick(events, self._wall())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Só o tipo: a mensagem de um erro futuro poderia trazer a URL secreta da agenda.
                log.warning("calendar watch tick failed error=%s", type(exc).__name__)
            await asyncio.sleep(TICK_S)

    async def _load(self) -> list[CalendarEvent]:
        if (await self._store.get_setting(SETTING_KEY)) == "0":
            return []
        url = (await self._store.get_setting(CALENDAR_KEY)) or ""
        if not url:
            self._events, self._fetched_at = [], None
            return []
        now = self._clock()
        if self._fetched_at is None or now - self._fetched_at >= REFRESH_S:
            self._fetched_at = now
            try:
                self._events = await self._calendar.upcoming(url, hours=LOOKAHEAD_HOURS)
            except CalendarError as exc:
                # Nunca loga a URL: é o endereço secreto da agenda.
                log.warning("calendar watch fetch failed reason=%s", exc)
        return self._events

    async def tick(self, events: Sequence[CalendarEvent], now: datetime) -> str | None:
        """Começa a gravar o evento que está começando agora. Devolve o id da sessão."""
        if self._is_recording():
            self._mark_covered(events)
            return None
        if not self._asr_ready():
            return None
        # Livre/ocupado não diz que é reunião: só grava sozinho se o usuário ligou BUSY_KEY.
        busy = busy_only(events)
        if busy and (await self._store.get_setting(BUSY_KEY)) != "1":
            return None
        for event in events:
            key = _key(event)
            if key in self._fired or (not busy and not event.title.strip()):
                continue
            if not (event.start - EARLY <= now <= event.start + LATE and now < event.end):
                continue
            if event.end - event.start >= MAX_LENGTH:
                continue
            self._fired.add(key)
            # "" = título padrão do CaptureService; "Ocupado" não diz nada da reunião.
            title = "" if busy else event.title
            try:
                session_id = await self._start_capture(title, event.end)
            except Exception:
                log.exception("calendar auto start failed")
                return None
            if not session_id:
                return None
            log.info("calendar auto-started session=%s", session_id)
            if not title:  # O aviso mostra o título que a gravação ganhou ("Reunião <data> <hora>").
                session = await self._store.get_session(session_id)
                title = session.title if session else ""
            await self._bus.publish(
                {"type": "calendar", "status": "auto-started", "session_id": session_id, "title": title}
            )
            return session_id
        return None

    def _mark_covered(self, events: Sequence[CalendarEvent]) -> None:
        """Evento que a gravação ao vivo já cobre não volta a gravar quando ela parar.
        Cobre: mesmo fim planejado (botão "Gravar" do painel) ou gravação iniciada dentro
        do evento. Reunião seguida (B começa quando A acaba) não casa e continua valendo."""
        since, until = self._live_span()
        for event in events:
            same_end = until is not None and until == event.end
            began_inside = since is not None and event.start - EARLY <= since < event.end
            if same_end or began_inside:
                self._fired.add(_key(event))


def _key(event: CalendarEvent) -> str:
    return f"{event.uid}@{event.start.isoformat()}"


async def migrate_auto_record(store: SessionRepository) -> None:
    """Quem atualiza com agenda já conectada não passa a gravar sem saber: fica desligado
    e a tela oferece uma vez (LGPD art. 6, VI). Conexão nova grava "1" em setup.py."""
    if (await store.get_setting(CALENDAR_KEY)) and (await store.get_setting(SETTING_KEY)) is None:
        await store.set_setting(SETTING_KEY, "0")
        await store.set_setting(OFFER_KEY, "1")
