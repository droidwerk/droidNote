"""Detecção de reunião: o Zoom/Teams/navegador abriu o microfone? Avisa ou grava.

Modos (setting `meeting_detection`):
- "off": não observa nada.
- "ask" (padrão): avisa a UI, que oferece "Gravar".
- "auto": começa a gravar sozinho e para quando o app solta o microfone
  (só para as gravações que ele mesmo começou).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.application.bus import EventBus
from app.core.logging import get_logger

log = get_logger("meetings")

MODES = ("off", "ask", "auto")
DEFAULT_MODE = "ask"
POLL_SECONDS = 2.0
START_AFTER_S = 3.0
END_AFTER_S = 6.0


class MicUsageProbe(Protocol):
    def available(self) -> bool: ...

    def snapshot(self) -> list: ...


@dataclass
class MeetingState:
    active: bool = False
    app: str | None = None
    browser: bool = False
    since: datetime | None = None
    dismissed: bool = False
    auto_session_id: str | None = None
    apps: list[str] = field(default_factory=list)


class MeetingWatcher:
    def __init__(
        self,
        probe: MicUsageProbe,
        bus: EventBus,
        *,
        get_mode: Callable[[], Awaitable[str]],
        is_recording: Callable[[], bool],
        current_session: Callable[[], str | None],
        start_capture: Callable[[str], Awaitable[str | None]],
        stop_capture: Callable[[], Awaitable[None]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = probe
        self._bus = bus
        self._get_mode = get_mode
        self._is_recording = is_recording
        self._current_session = current_session
        self._start_capture = start_capture
        self._stop_capture = stop_capture
        self._clock = clock
        self.state = MeetingState()
        self._seen_at: float | None = None
        self._released_at: float | None = None
        self._task: asyncio.Task[None] | None = None

    def available(self) -> bool:
        return self._probe.available()

    def start(self) -> None:
        if not self.available() or self._task is not None:
            return
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
                mode = await self._get_mode()
                if mode != "off":
                    users = await asyncio.to_thread(self._probe.snapshot)
                    await self.tick(users, mode)
                elif self.state.active:
                    self._reset()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("meeting watcher tick failed")
            await asyncio.sleep(POLL_SECONDS)

    def _reset(self) -> None:
        self.state = MeetingState()
        self._seen_at = None
        self._released_at = None

    async def tick(self, users: list, mode: str) -> None:
        now = self._clock()
        using = [item for item in users if item.in_use]
        if using:
            self._released_at = None
            # App dedicado de reunião vence o navegador.
            using.sort(key=lambda item: item.browser)
            head = using[0]
            self.state.apps = sorted({item.app for item in using})
            if self._seen_at is None:
                self._seen_at = now
            if not self.state.active and now - self._seen_at >= START_AFTER_S:
                await self._begin(head.app, head.browser, mode)
            return
        self._seen_at = None
        if not self.state.active:
            return
        if self._released_at is None:
            self._released_at = now
            return
        if now - self._released_at >= END_AFTER_S:
            await self._end()

    async def _begin(self, app: str, browser: bool, mode: str) -> None:
        self.state = MeetingState(
            active=True,
            app=app,
            browser=browser,
            since=datetime.now(tz=UTC),
            apps=self.state.apps,
        )
        recording = self._is_recording()
        log.info("meeting detected app=%s mode=%s recording=%s", app, mode, recording)
        await self._bus.publish(self._event("detected", mode=mode, recording=recording))
        if mode == "auto" and not recording:
            try:
                session_id = await self._start_capture(app)
            except Exception:
                log.exception("auto start failed app=%s", app)
                session_id = None
            if session_id:
                self.state.auto_session_id = session_id
                await self._bus.publish(self._event("auto-started", session_id=session_id))

    async def _end(self) -> None:
        app = self.state.app
        auto_session = self.state.auto_session_id
        stopped = False
        if auto_session and self._is_recording() and self._current_session() == auto_session:
            try:
                await self._stop_capture()
                stopped = True
            except Exception:
                log.exception("auto stop failed app=%s", app)
        log.info("meeting ended app=%s auto_stopped=%s", app, stopped)
        await self._bus.publish(
            {"type": "meeting", "status": "ended", "app": app, "auto_stopped": stopped, "recording": self._is_recording()}
        )
        self._reset()

    async def dismiss(self) -> None:
        self.state.dismissed = True
        await self._bus.publish(self._event("dismissed"))

    def status(self) -> dict[str, object]:
        return {
            "available": self.available(),
            "active": self.state.active,
            "app": self.state.app,
            "browser": self.state.browser,
            "since": self.state.since.isoformat() if self.state.since else None,
            "dismissed": self.state.dismissed,
            "auto_session_id": self.state.auto_session_id,
            "apps": self.state.apps,
        }

    def _event(self, status: str, **extra: object) -> dict[str, object]:
        return {"type": "meeting", "status": status, **self.status(), **extra}


def normalize_mode(value: str | None) -> str:
    cleaned = (value or DEFAULT_MODE).strip().lower()
    return cleaned if cleaned in MODES else DEFAULT_MODE
