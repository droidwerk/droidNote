from __future__ import annotations

from app.core.hardware import (
    disk_has_room,
    estimate_download_gb,
    free_disk_gb,
    suggest_note_model,
    suggest_whisper_model,
    total_ram_gb,
)


def test_note_model_follows_available_ram() -> None:
    assert suggest_note_model(32) == "gemma3:12b"
    assert suggest_note_model(16) == "qwen3:8b"
    assert suggest_note_model(8) == "qwen3:4b"
    assert suggest_note_model(4) == "qwen2.5:3b"


def test_unknown_ram_falls_back_to_a_safe_model() -> None:
    assert suggest_note_model(0) == "qwen3:4b"
    assert suggest_whisper_model(0, cuda=False) == "small"


def test_whisper_suggestion_needs_vram_for_turbo() -> None:
    assert suggest_whisper_model(16, cuda=True, vram=8) == "large-v3-turbo"
    assert suggest_whisper_model(16, cuda=True, vram=4) == "small"
    assert suggest_whisper_model(16, cuda=True, vram=0) == "small"
    assert suggest_whisper_model(16, cuda=False, vram=12) == "small"


def test_this_machine_reports_some_ram() -> None:
    assert total_ram_gb() > 0


def test_estimate_download_skips_installed() -> None:
    assert (
        estimate_download_gb(
            whisper_id="small",
            note_id="qwen3:8b",
            need_installer=False,
            whisper_installed=True,
            note_installed=True,
        )
        == 0
    )


def test_estimate_download_adds_installer_and_models() -> None:
    total = estimate_download_gb(
        whisper_id="small",
        note_id="qwen3:8b",
        need_installer=True,
        whisper_installed=False,
        note_installed=False,
    )
    assert total > 6


def test_disk_has_room_when_unmeasurable(tmp_path) -> None:
    ok, _free, needed = disk_has_room(tmp_path, 0)
    assert ok is True
    assert needed == 0


def test_this_machine_reports_free_disk(tmp_path) -> None:
    assert free_disk_gb(tmp_path) > 0
