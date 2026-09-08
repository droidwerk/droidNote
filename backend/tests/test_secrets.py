from __future__ import annotations

from app.core.secrets import protect_setting, unprotect_setting


def test_protect_setting_roundtrip() -> None:
    stored = protect_setting("asr_api_key", "sk-live-secret-key")
    assert stored != "sk-live-secret-key"
    assert "sk-live-secret-key" not in stored
    assert unprotect_setting("asr_api_key", stored) == "sk-live-secret-key"


def test_protect_setting_ignores_plain_keys() -> None:
    assert protect_setting("language", "pt") == "pt"


def test_unprotect_migrates_legacy_plaintext() -> None:
    assert unprotect_setting("asr_api_key", "sk-legacy") == "sk-legacy"
