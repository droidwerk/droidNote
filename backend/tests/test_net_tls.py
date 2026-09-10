from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from app.application.setup import _friendly_download_error
from app.core import net_tls


def test_bundle_joins_certifi_and_system_certificates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in net_tls.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    fake = ssl.DER_cert_to_PEM_cert(b"\x30\x03corporate-ca")
    monkeypatch.setattr(net_tls, "_certifi_pem", lambda: ["-----BEGIN CERTIFICATE-----\npublic\n"])
    monkeypatch.setattr(net_tls, "_system_certificates", lambda: [fake])

    bundle = net_tls.install_system_trust(tmp_path)

    assert bundle is not None
    body = bundle.read_text(encoding="utf-8")
    assert "public" in body
    assert fake in body
    for key in net_tls.ENV_KEYS:
        assert net_tls.os.environ[key] == str(bundle)


def test_user_bundle_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    own = tmp_path / "own.pem"
    own.write_text("-----BEGIN CERTIFICATE-----\nmine\n", encoding="utf-8")
    for key in net_tls.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", str(own))

    assert net_tls.install_system_trust(tmp_path) == own
    assert not (tmp_path / "certs").exists()


def test_certificate_error_explains_https_inspection() -> None:
    exc = RuntimeError(
        "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "self-signed certificate in certificate chain (_ssl.c:1081)"
    )
    message = _friendly_download_error(exc, kind="whisper")
    assert "certificado" in message.lower()
    assert "internet falhou" not in message.lower()
