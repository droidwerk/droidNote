from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.infrastructure.llm.ollama_manager import list_disk_ollama_models, verify_sha256


def test_verify_sha256_accepts_matching_digest(tmp_path: Path) -> None:
    path = tmp_path / "OllamaSetup.exe"
    payload = b"droidnote-ollama"
    path.write_bytes(payload)
    verify_sha256(path, hashlib.sha256(payload).hexdigest())


def test_verify_sha256_rejects_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "OllamaSetup.exe"
    path.write_bytes(b"droidnote-ollama")
    with pytest.raises(RuntimeError, match="adulterado"):
        verify_sha256(path, "00" * 32)


def test_list_disk_ollama_models_reads_manifests(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "models"
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "8b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OLLAMA_MODELS", str(root))
    monkeypatch.setattr("app.infrastructure.llm.ollama_manager.Path.home", lambda: tmp_path / "empty-home")
    assert "qwen3:8b" in list_disk_ollama_models()
