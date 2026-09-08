from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PRODUCT_DIR_NAME = "DroidNote"
DEV_DIR_NAME = "DroidNote-dev"


def _appdata_base() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if os.uname().sysname == "Darwin":  # pragma: no cover
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))  # pragma: no cover


def _is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def migrate_legacy_dev_data(base: Path | None = None) -> None:
    """Move the old shared AppData folder to the dev profile so the installed app stays empty."""
    if _is_packaged():
        return
    root = base or _appdata_base()
    legacy = root / PRODUCT_DIR_NAME
    dest = root / DEV_DIR_NAME
    if dest.exists() or not legacy.exists():
        return
    try:
        legacy.rename(dest)
    except OSError:
        return


def default_data_dir() -> Path:
    base = _appdata_base()
    migrate_legacy_dev_data(base)
    return base / (PRODUCT_DIR_NAME if _is_packaged() else DEV_DIR_NAME)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DROIDNOTE_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 0
    token: str = ""
    data_dir: Path = Field(default_factory=default_data_dir)
    whisper_model: str = "small"
    whisper_device: str = "auto"
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    provider: str = "neste_pc"
    asr_cloud_model: str = "whisper-1"
    llm_cloud_model: str = "gpt-4o-mini"
    language: str = "pt"
    sample_rate: int = 16_000
    window_seconds: float = 20.0
    overlap_seconds: float = 1.0
    recordings_dir: Path | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "droidnote.db"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def runtime_path(self) -> Path:
        return self.data_dir / "runtime.json"

    def resolve_recordings_dir(self) -> Path:
        if self.recordings_dir:
            return Path(self.recordings_dir)
        return self.data_dir / "recordings"


def session_recording_path(settings: Settings, session_id: str) -> Path:
    return settings.resolve_recordings_dir() / f"{session_id}.wav"


def parse_recordings_dir(raw: str, data_dir: Path) -> Path:
    cleaned = raw.strip().strip('"')
    if not cleaned:
        return data_dir / "recordings"
    path = Path(cleaned).expanduser()
    if not path.is_absolute():
        path = (data_dir / path).resolve()
    else:
        path = path.resolve()
    if path.exists() and path.is_file():
        raise ValueError("Caminho aponta para um arquivo, não uma pasta")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Não foi possível usar esta pasta de gravações: {exc}") from exc
    return path


@lru_cache
def get_settings() -> Settings:
    migrate_legacy_dev_data()
    settings = Settings()
    if _is_packaged():
        settings.host = "127.0.0.1"
    if not settings.token:
        settings.token = os.environ.get("DROIDNOTE_TOKEN") or secrets.token_urlsafe(32)
        os.environ["DROIDNOTE_TOKEN"] = settings.token
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    settings.resolve_recordings_dir().mkdir(parents=True, exist_ok=True)
    return settings
