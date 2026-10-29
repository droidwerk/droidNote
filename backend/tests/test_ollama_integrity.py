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


async def test_catalog_tag_counts_as_installed_when_latest_has_the_same_weights(tmp_path: Path, monkeypatch) -> None:
    from app.infrastructure.llm.ollama_manager import find_installed_aliases, local_model_digests

    root = tmp_path / "models"
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "gemma4" / "latest"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '{"layers": [{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:aaa"},'
        ' {"mediaType": "application/vnd.ollama.image.license", "digest": "sha256:lic"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("OLLAMA_MODELS", str(root))
    monkeypatch.setattr("app.infrastructure.llm.ollama_manager.Path.home", lambda: tmp_path / "empty-home")
    assert local_model_digests() == {"gemma4:latest": "sha256:aaa"}

    asked: list[str] = []

    async def remote(model_id: str) -> str | None:
        asked.append(model_id)
        return {"gemma4:e4b": "sha256:aaa", "gemma4:12b": "sha256:bbb"}.get(model_id)

    aliases = await find_installed_aliases(
        ["gemma4:e4b", "gemma4:12b", "qwen3:8b"], {"gemma4:latest"}, remote_digest=remote
    )
    assert aliases == {"gemma4:e4b": "gemma4:latest"}
    # Família sem nada instalado não gera consulta ao registro.
    assert asked == ["gemma4:e4b", "gemma4:12b"]
