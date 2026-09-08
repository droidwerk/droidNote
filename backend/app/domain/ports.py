from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from app.domain.models import (
    AudioChunk,
    Person,
    Session,
    SetupStatus,
    Summary,
    TranscriptSegment,
)

AudioCallback = Callable[[AudioChunk], None]


class AudioCapturePort(Protocol):
    def list_devices(self) -> list[dict[str, str]]: ...

    def start(
        self,
        callback: AudioCallback,
        *,
        microphone_id: str | None = None,
        loopback_id: str | None = None,
        mic_only: bool = False,
    ) -> None: ...

    def stop(self) -> None: ...

    def probe(self) -> dict[str, bool | str]: ...


class AsrPort(Protocol):
    def is_ready(self) -> bool: ...

    def download(self, on_progress: Callable[[int, str], None] | None = None) -> None: ...

    def load(self) -> None: ...

    def unload(self) -> None: ...

    def transcribe_window(
        self,
        samples: Sequence[float],
        sample_rate: int,
        *,
        language: str | None = None,
    ) -> tuple[str, str | None]: ...


class LlmPort(Protocol):
    async def status(self) -> SetupStatus: ...  # type: ignore[override]

    async def ensure_ready(self, on_progress: Callable[[int, str], None] | None = None) -> None: ...

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str: ...

    async def generate_json_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str: ...

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str: ...

    async def generate_text_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str: ...


class SessionRepository(Protocol):
    async def create_session(self, session: Session) -> None: ...

    async def get_session(self, session_id: str) -> Session | None: ...

    async def list_sessions(self) -> list[Session]: ...

    async def update_session(self, session: Session) -> None: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def add_segment(self, segment: TranscriptSegment) -> None: ...

    async def list_segments(self, session_id: str) -> list[TranscriptSegment]: ...

    async def search(self, query: str, session_id: str | None = None) -> list[TranscriptSegment]: ...

    async def save_summary(self, summary: Summary) -> None: ...

    async def get_summary(self, session_id: str) -> Summary | None: ...

    async def get_setting(self, key: str) -> str | None: ...

    async def set_setting(self, key: str, value: str) -> None: ...

    async def list_people(self) -> list[Person]: ...

    async def create_person(self, name: str) -> Person: ...

    async def delete_person(self, person_id: str) -> None: ...

    async def get_person(self, person_id: str) -> Person | None: ...

    async def list_people_by_ids(self, person_ids: Sequence[str]) -> list[Person]: ...

    async def list_session_participants(self, session_id: str) -> list[Person]: ...

    async def set_session_participants(self, session_id: str, person_ids: Sequence[str]) -> None: ...

    async def get_segment(self, segment_id: str) -> TranscriptSegment | None: ...

    async def set_segment_speaker(self, segment_id: str, speaker_id: str | None) -> TranscriptSegment | None: ...

    async def save_segment(self, segment: TranscriptSegment) -> TranscriptSegment | None: ...
