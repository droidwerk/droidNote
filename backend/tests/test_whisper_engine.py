from __future__ import annotations

from app.infrastructure.asr.whisper_engine import (
    _is_cuda_runtime_error,
    _select_device,
    _whisper_importable,
    build_asr_prompt,
    filter_transcript,
    whisper_language_arg,
)


def test_whisper_library_is_importable() -> None:
    assert _whisper_importable() is True


def test_select_device_uses_cpu_when_cublas_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.infrastructure.asr.whisper_engine._cublas_available",
        lambda: False,
    )
    assert _select_device("auto") == ("cpu", "int8")


def test_select_device_cpu_policy_ignores_gpu(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.infrastructure.asr.whisper_engine._cuda_usable",
        lambda: True,
    )
    assert _select_device("cpu") == ("cpu", "int8")


def test_select_device_force_cpu() -> None:
    assert _select_device("auto", force_cpu=True) == ("cpu", "int8")


def test_cuda_runtime_error_detects_missing_cublas() -> None:
    err = RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
    assert _is_cuda_runtime_error(err) is True
    assert _is_cuda_runtime_error(RuntimeError("unrelated")) is False


def test_filter_drops_cyrillic_when_language_locked() -> None:
    assert filter_transcript("Мы молодец разве", "pt") == ""
    assert filter_transcript("Olá pessoal", "pt") == "Olá pessoal"


def test_filter_drops_hum_loops() -> None:
    assert filter_transcript("hum, hum, hum, hum, hum") == ""


def test_filter_drops_prompt_echo() -> None:
    assert filter_transcript("Do not invent phrases that were not said.") == ""
    assert filter_transcript("Olá pessoal", "pt") == "Olá pessoal"


def test_prompt_locks_language_without_participant_names() -> None:
    prompt = build_asr_prompt("pt")
    assert "português brasileiro" in prompt
    assert "Participantes" not in prompt
    assert "[Pessoa" not in prompt
    assert "Do not invent" not in prompt
    assert build_asr_prompt("auto") == ""
    assert build_asr_prompt(None) == ""


def test_whisper_language_arg_auto_is_none() -> None:
    assert whisper_language_arg("auto") is None
    assert whisper_language_arg("pt") == "pt"


def test_catalog_detail_is_size_only(tmp_path) -> None:
    from app.infrastructure.asr.whisper_engine import catalog_whisper_models

    models = tmp_path / "models"
    rows = catalog_whisper_models(models, "small")
    small = next(row for row in rows if row["id"] == "small")
    assert small["installed"] is False
    assert small["detail"] == ""
    assert "neste PC" not in str(small["label"])


def test_is_ready_requires_complete_marker(tmp_path) -> None:
    from app.infrastructure.asr.whisper_engine import WhisperEngine

    models = tmp_path / "models"
    blob = models / "models--Systran--faster-whisper-small" / "snapshots" / "abc"
    blob.mkdir(parents=True)
    (blob / "model.bin").write_bytes(b"incomplete")
    engine = WhisperEngine("small", models)
    assert engine.is_ready() is False
    engine._mark_complete()
    assert engine.is_ready() is True
    assert engine._complete_marker().is_file()
