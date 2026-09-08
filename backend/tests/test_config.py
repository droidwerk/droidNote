from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core.config import DEV_DIR_NAME, PRODUCT_DIR_NAME, default_data_dir, migrate_legacy_dev_data


def test_dev_data_dir_is_isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert default_data_dir() == tmp_path / DEV_DIR_NAME


def test_packaged_data_dir_is_product(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert default_data_dir() == tmp_path / PRODUCT_DIR_NAME


def test_legacy_shared_folder_moves_to_dev(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delattr(sys, "frozen", raising=False)
    legacy = tmp_path / PRODUCT_DIR_NAME
    legacy.mkdir()
    (legacy / "droidnote.db").write_bytes(b"dev")
    migrate_legacy_dev_data(tmp_path)
    dest = tmp_path / DEV_DIR_NAME
    assert dest.is_dir()
    assert (dest / "droidnote.db").read_bytes() == b"dev"
    assert not legacy.exists()


def test_packaged_does_not_steal_legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    legacy = tmp_path / PRODUCT_DIR_NAME
    legacy.mkdir()
    (legacy / "droidnote.db").write_bytes(b"keep")
    migrate_legacy_dev_data(tmp_path)
    assert (legacy / "droidnote.db").read_bytes() == b"keep"
    assert not (tmp_path / DEV_DIR_NAME).exists()


def test_packaged_forces_loopback_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("DROIDNOTE_HOST", "0.0.0.0")
    monkeypatch.setenv("DROIDNOTE_TOKEN", "loop-token")
    monkeypatch.setattr("app.core.config._is_packaged", lambda: True)
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.host == "127.0.0.1"
    finally:
        get_settings.cache_clear()
