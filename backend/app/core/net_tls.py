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
            _write_atomic(bundle, body)
    except OSError as exc:
        if not bundle.is_file():
            log.exception("could not write tls bundle path=%s", bundle)
            return None
        # Outro processo do app está com o arquivo aberto: o bundle anterior serve.
        log.warning("tls bundle kept as is path=%s error=%s", bundle, exc)

    for key in ENV_KEYS:
        os.environ[key] = str(bundle)
    log.info("tls bundle ready certs=%d path=%s", len(pem), bundle)
    return bundle


def _write_atomic(path: Path, body: str) -> None:
    """Grava num arquivo ao lado e troca de uma vez: quem lê o bundle nesse
    instante (outro processo do app, um teste) nunca vê um PEM pela metade."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(body, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


_context_cache: tuple[tuple[str, int, int], ssl.SSLContext] | None = None


def ssl_verify() -> ssl.SSLContext | bool:
    """Valor de `verify=` para clientes httpx.

    O httpx não lê essas variáveis de ambiente, então o bundle do PC entra
    explicitamente, já carregado num contexto (reaproveitado enquanto o arquivo
    não muda). Sem bundle, ou com um que não carrega, fica o padrão da biblioteca.
    """
    global _context_cache
    bundle = _user_bundle()
    if bundle is None:
        return True
    try:
        stat = bundle.stat()
        key = (str(bundle), stat.st_mtime_ns, stat.st_size)
        if _context_cache is not None and _context_cache[0] == key:
            return _context_cache[1]
        context = ssl.create_default_context(cafile=str(bundle))
    except (OSError, ssl.SSLError, ValueError) as exc:
        log.warning("tls bundle unreadable, using library default path=%s error=%s", bundle, exc)
        return True
    _context_cache = (key, context)
    return context


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
    # Ordem fixa: o Windows devolve o repositório em ordem variável e o bundle
    # seria reescrito a cada abertura do app sem ter mudado de verdade.
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
    return sorted(out)
