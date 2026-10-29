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
    assert suggest_note_model(40, vram=0) == "qwen3.6:35b-a3b"
    assert suggest_note_model(24, vram=0) == "gemma4:26b"
    assert suggest_note_model(16, vram=0) == "gemma4:12b"
    assert suggest_note_model(8, vram=0) == "gemma4:e4b"
    assert suggest_note_model(4, vram=0) == "gemma4:e2b"


def test_note_model_fits_the_graphics_card_when_there_is_one() -> None:
    # 16 GB de RAM pediria o 12B (7,7 GB), mas numa placa de 8 GB ele transborda: fica o E4B.
    assert suggest_note_model(16, vram=8) == "gemma4:e4b"
    assert suggest_note_model(16, vram=12) == "gemma4:12b"
    assert suggest_note_model(16, vram=4) == "gemma4:e2b"
    # Modelos MoE grandes seguem a RAM: rodam bem mesmo fora da placa.
    assert suggest_note_model(40, vram=8) == "qwen3.6:35b-a3b"


def test_unknown_ram_falls_back_to_a_safe_model() -> None:
    assert suggest_note_model(0, vram=0) == "gemma4:e4b"
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
