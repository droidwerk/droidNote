from __future__ import annotations

from pathlib import Path

from app.core.i18n import (
    normalize_capture_language,
    normalize_ui_language,
    read_install_language,
    ui_message,
)
from app.infrastructure.asr.whisper_engine import filter_transcript, whisper_language_arg

import pytest
from httpx import AsyncClient

from tests.conftest import auth


def test_normalize_capture_accepts_new_languages() -> None:
    for code in ("pt", "en", "es", "it", "de", "fr", "ru", "auto"):
        assert normalize_capture_language(code) == code
    assert normalize_capture_language("pl") == "pt"
    assert normalize_capture_language("") == "pt"


def test_normalize_ui_rejects_auto() -> None:
    assert normalize_ui_language("ru") == "ru"
    assert normalize_ui_language("auto") == "pt"
    assert normalize_ui_language("xx") == "pt"


def test_filter_keeps_cyrillic_when_locked_to_russian() -> None:
    assert filter_transcript("Мы молодец разве", "ru") == "Мы молодец разве"
    assert filter_transcript("Мы молодец разве", "pt") == ""
    assert filter_transcript("Olá pessoal", "pt") == "Olá pessoal"


def test_filter_drops_cjk_when_locked_to_russian() -> None:
    assert filter_transcript("こんにちは", "ru") == ""


def test_whisper_language_arg_russian() -> None:
    assert whisper_language_arg("ru") == "ru"
    assert whisper_language_arg("it") == "it"
    assert whisper_language_arg("auto") is None


def test_ui_message_falls_back_to_portuguese() -> None:
    assert ui_message("pt", "session_missing") == "Sessão não encontrada"
    assert ui_message("en", "session_missing") == "Session not found"
    assert ui_message("xx", "session_missing") == "Sessão não encontrada"


def test_read_install_language_from_langid(tmp_path: Path) -> None:
    path = tmp_path / "install-lang.txt"
    path.write_text("1049", encoding="utf-8")
    assert read_install_language(tmp_path) == "ru"
    path.write_text("en", encoding="utf-8")
    assert read_install_language(tmp_path) == "en"
    assert read_install_language(tmp_path / "missing") is None


@pytest.mark.asyncio
async def test_settings_persist_ui_and_capture_language(client: AsyncClient) -> None:
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"language": "ru", "ui_language": "de"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["language"] == "ru"
    assert body["ui_language"] == "de"

    listed = await client.get("/setup/settings", headers=auth())
    assert listed.json()["language"] == "ru"
    assert listed.json()["ui_language"] == "de"

    rejected = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"language": "pl", "ui_language": "auto"},
    )
    assert rejected.status_code == 200
    again = rejected.json()
    assert again["language"] == "ru"
    assert again["ui_language"] == "de"

