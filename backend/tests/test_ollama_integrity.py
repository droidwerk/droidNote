from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.infrastructure.llm.ollama_manager import verify_sha256


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
