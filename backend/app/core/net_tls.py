"""Confiança TLS do PC onde o DroidNote roda.

Rede corporativa, proxy e antivírus com inspeção de HTTPS reassinam o tráfego com
uma CA própria, que existe apenas no repositório de certificados do Windows. As
bibliotecas HTTP do Python (`requests`, usada pelo huggingface_hub, e `httpx`)
confiam só no bundle do `certifi`, então o download do Whisper falha com
CERTIFICATE_VERIFY_FAILED / "self-signed certificate in certificate chain".

Aqui as CAs do sistema entram num bundle único, junto com o certifi, e o caminho
desse bundle vai para as variáveis que essas bibliotecas leem.
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path

from app.core.logging import get_logger

log = get_logger("tls")

# Cada biblioteca lê uma variável diferente; o bundle é o mesmo.
ENV_KEYS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")

_WINDOWS_STORES = ("ROOT", "CA")
_SERVER_AUTH_OID = "1.3.6.1.5.5.7.3.1"


def install_system_trust(data_dir: Path) -> Path | None:
    """Aponta as libs HTTP para um bundle com certifi + CAs do sistema.

    Devolve o caminho do bundle, ou None quando não há nada a fazer (o usuário já
    definiu um bundle próprio, ou o sistema não expõe o repositório de certificados).
    """
    existing = _user_bundle()
    if existing is not None:
        log.info("tls bundle from environment path=%s", existing)
        return existing

    system = _system_certificates()
    if not system:
        return None

    pem = _certifi_pem() + system
    bundle = Path(data_dir) / "certs" / "trust-bundle.pem"
    body = "".join(pem)
    try:
        bundle.parent.mkdir(parents=True, exist_ok=True)
        if not bundle.is_file() or bundle.read_text(encoding="utf-8") != body:
            bundle.write_text(body, encoding="utf-8")
    except OSError:
        log.exception("could not write tls bundle path=%s", bundle)
        return None

    for key in ENV_KEYS:
        os.environ[key] = str(bundle)
    log.info("tls bundle ready certs=%d path=%s", len(pem), bundle)
    return bundle


def ssl_verify() -> str | bool:
    """Valor de `verify=` para clientes httpx.

    O httpx não lê essas variáveis de ambiente, então o bundle do PC entra
    explicitamente; sem bundle, fica o padrão da biblioteca.
    """
    bundle = _user_bundle()
    return str(bundle) if bundle else True


def _user_bundle() -> Path | None:
    for key in ENV_KEYS:
        raw = (os.environ.get(key) or "").strip()
        if raw and Path(raw).is_file():
            return Path(raw)
    return None


def _certifi_pem() -> list[str]:
    try:
        import certifi
    except Exception:
        return []
    try:
        return [Path(certifi.where()).read_text(encoding="utf-8")]
    except OSError:
        return []


def _system_certificates() -> list[str]:
    """CAs de servidor do repositório do Windows, em PEM.

    `ssl.enum_certificates` só existe no Windows; em outros sistemas o bundle do
    OpenSSL já cobre o caso e não há o que somar.
    """
    enumerate_store = getattr(ssl, "enum_certificates", None)
    if enumerate_store is None:
        return []
    out: list[str] = []
    seen: set[bytes] = set()
    for store in _WINDOWS_STORES:
        try:
            entries = enumerate_store(store)
        except Exception:
            continue
        for der, encoding, trust in entries:
            if encoding != "x509_asn" or der in seen:
                continue
            if trust is not True and _SERVER_AUTH_OID not in (trust or ()):
                continue
            seen.add(der)
            try:
                out.append(ssl.DER_cert_to_PEM_cert(der))
            except Exception:
                continue
    return out
