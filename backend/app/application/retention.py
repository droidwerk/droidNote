"""Retenção: apaga áudio e/ou transcrição de gravações antigas.

Dois prazos independentes, em dias (0 = guardar para sempre). A transcrição
apagada leva junto as vozes da sessão; ata, notas e tarefas continuam — é o
que a pessoa quer guardar de uma reunião. Gravação em andamento nunca entra.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.logging import get_logger
from app.infrastructure.persistence.sqlite import SqliteStore

log = get_logger("retention")

AUDIO_KEY = "retention_audio_days"
TRANSCRIPT_KEY = "retention_transcript_days"
CHOICES = (0, 7, 14, 30, 60, 90, 180, 365)


@dataclass(frozen=True)
class RetentionReport:
    audio_files: int
    transcripts: int
    audio_days: int
    transcript_days: int


def parse_days(raw: str | int | None) -> int:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, 3650))


class RetentionService:
    def __init__(
        self,
        store: SqliteStore,
        recordings_path: Callable[[str], Path],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._recordings_path = recordings_path
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    async def policy(self) -> tuple[int, int]:
        return (
            parse_days(await self._store.get_setting(AUDIO_KEY)),
            parse_days(await self._store.get_setting(TRANSCRIPT_KEY)),
        )

    async def run(
        self,
        *,
        dry_run: bool = False,
        audio_days: int | None = None,
        transcript_days: int | None = None,
    ) -> RetentionReport:
        saved_audio, saved_transcript = await self.policy()
        audio = saved_audio if audio_days is None else parse_days(audio_days)
        transcript = saved_transcript if transcript_days is None else parse_days(transcript_days)
        now = self._clock()
        audio_count = 0
        transcript_count = 0
        for session in await self._store.list_sessions():
            if session.status == "recording":
                continue
            age = now - (session.ended_at or session.started_at)
            if audio and age > timedelta(days=audio):
                path = self._recordings_path(session.id)
                if path.is_file():
                    audio_count += 1
                    if not dry_run:
                        try:
                            path.unlink()
                        except OSError:
                            log.warning("retention could not delete audio session=%s", session.id)
                            audio_count -= 1
            if transcript and age > timedelta(days=transcript) and session.transcript_purged_at is None:
                transcript_count += 1
                if not dry_run:
                    await self._store.purge_transcript(session.id)
        if not dry_run and (audio_count or transcript_count):
            log.info("retention removed audio=%d transcripts=%d", audio_count, transcript_count)
        return RetentionReport(audio_count, transcript_count, audio, transcript)
