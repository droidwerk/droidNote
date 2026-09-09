from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx

from app.application.prompts import SYSTEM_PROMPT
from app.core.distribution import OLLAMA_SETUP_SHA256, OLLAMA_SETUP_URL, OLLAMA_SETUP_VERSION
from app.core.logging import get_logger
from app.core.user_errors import explain
from app.domain.models import SetupComponentStatus

log = get_logger("ollama")

# Modelos locais que seguem instrução e devolvem JSON válido de forma confiável.
# Ordenado do mais recomendado para o mais leve.
OLLAMA_CATALOG: tuple[tuple[str, str], ...] = (
    ("qwen3:8b", "Qwen3 8B — recomendado, JSON confiável (~6 GB de RAM)"),
    ("gemma3:12b", "Gemma 3 12B — melhor português, exige ~9 GB"),
    ("llama3.1:8b", "Llama 3.1 8B — alternativa madura (~6 GB)"),
    ("qwen3:4b", "Qwen3 4B — para máquinas modestas (~4 GB)"),
    ("qwen2.5:3b", "Qwen2.5 3B — mais leve, notas mais pobres (~3 GB)"),
)


class OllamaManager:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.component = SetupComponentStatus()

    def set_model(self, model: str) -> None:
        self.model = model

    async def is_server_up(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError:
            payload = {"models": []}
        for item in payload.get("models") or []:
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            size = item.get("size")
            detail = _format_bytes(size) if isinstance(size, int) else ""
            rows.append({"id": name, "label": name, "detail": detail})
        for name in list_disk_ollama_models():
            if name in seen:
                continue
            seen.add(name)
            rows.append({"id": name, "label": name, "detail": ""})
        return rows

    async def has_model(self) -> bool:
        models = await self.list_models()
        names = {item["id"] for item in models}
        return self.model in names or any(name.startswith(self.model) for name in names)

    def find_binary(self) -> str | None:
        found = shutil.which("ollama")
        if found:
            return found
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Ollama" / "ollama.exe",
        ]
        for path in candidates:
            if path.is_file():
                return str(path)
        return None

    async def status_component(self) -> SetupComponentStatus:
        if await self.is_server_up() and await self.has_model():
            self.component = SetupComponentStatus(status="ready", progress=100, message="Ollama pronto")
            return self.component
        if await self.is_server_up():
            self.component = SetupComponentStatus(
                status="missing",
                progress=40,
                message=f"Servidor no ar; modelo {self.model} ainda não baixado",
            )
            return self.component
        if self.find_binary():
            self.component = SetupComponentStatus(
                status="missing",
                progress=20,
                message="Ollama instalado, servidor parado",
            )
            return self.component
        if self.component.status in {"downloading", "installing"}:
            return self.component
        self.component = SetupComponentStatus(status="missing", progress=0, message="Ollama não encontrado")
        return self.component

    async def ensure_ready(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        def report(progress: int, message: str) -> None:
            self.component = SetupComponentStatus(
                status="installing" if progress < 100 else "ready",
                progress=progress,
                message=message,
            )
            if on_progress:
                on_progress(progress, message)

        if await self.is_server_up() and await self.has_model():
            report(100, "Ollama pronto")
            return

        binary = self.find_binary()
        if binary is None:
            report(5, "Baixando o instalador do Ollama")
            await asyncio.to_thread(self._install_windows)
            binary = self.find_binary()
            if binary is None:
                self.component = SetupComponentStatus(
                    status="error",
                    progress=0,
                    message=explain(
                        "O instalador do Ollama rodou, mas o programa não apareceu neste PC.",
                        severe=True,
                        app_will="O DroidNote não tenta executar um segundo instalador agora.",
                        user_can="Baixe em https://ollama.com/download, instale e toque em Tentar de novo.",
                    ),
                )
                raise RuntimeError(self.component.message)

        if not await self.is_server_up():
            report(35, "Iniciando o servidor Ollama")
            await asyncio.to_thread(self._serve, binary)
            for _ in range(30):
                if await self.is_server_up():
                    break
                await asyncio.sleep(0.5)

        if not await self.is_server_up():
            self.component = SetupComponentStatus(
                status="error",
                progress=0,
                message=explain(
                    "O Ollama está instalado, mas o servidor local não respondeu.",
                    severe=True,
                    app_will="O DroidNote não gera notas até o servidor subir.",
                    user_can="Abra o Ollama pelo menu Iniciar ou toque em Tentar de novo. Se um antivírus bloqueou a porta, permita o ollama.exe.",
                ),
            )
            raise RuntimeError(self.component.message)

        if not await self.has_model():
            report(50, f"Baixando modelo {self.model}")
            await self._pull(on_progress=report)

        report(100, "Ollama pronto")

    def build_payload(
        self,
        prompt: str,
        *,
        stream: bool,
        format_json: bool = True,
        system: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "system": system or SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": 0},
        }
        if format_json:
            payload["format"] = "json"
        payload["think"] = False
        return payload

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=self.build_payload(prompt, stream=False, system=system),
            )
            response.raise_for_status()
            return str(response.json().get("response") or "")

    async def generate_json_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str:
        return await self._stream(prompt, on_token, format_json=True, system=system)

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=self.build_payload(prompt, stream=False, format_json=False, system=system),
            )
            response.raise_for_status()
            return str(response.json().get("response") or "")

    async def generate_text_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        system: str | None = None,
    ) -> str:
        return await self._stream(prompt, on_token, format_json=False, system=system)

    async def _stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        *,
        format_json: bool,
        system: str | None,
    ) -> str:
        chunks: list[str] = []
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=self.build_payload(
                    prompt, stream=True, format_json=format_json, system=system
                ),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    token = str(payload.get("response") or "")
                    if token:
                        chunks.append(token)
                        on_token(token)
        return "".join(chunks)

    def _install_windows(self) -> None:
        self.component = SetupComponentStatus(
            status="downloading",
            progress=10,
            message="Baixando o Ollama",
        )
        installer: Path | None = None
        try:
            installer = _download_installer()
            verify_sha256(installer, OLLAMA_SETUP_SHA256)
            self.component = SetupComponentStatus(
                status="installing",
                progress=25,
                message="Instalando o Ollama",
            )
            completed = subprocess.run(
                [str(installer), "/VERYSILENT", "/NORESTART"],
                check=False,
                capture_output=True,
                timeout=600,
            )
            if completed.returncode != 0:
                log.error("ollama installer failed code=%s", completed.returncode)
                raise RuntimeError(
                    explain(
                        "A instalação silenciosa do Ollama falhou.",
                        severe=True,
                        app_will="Nenhum motor de notas extra foi ligado.",
                        user_can="Baixe em https://ollama.com/download, instale e toque em Tentar de novo.",
                    )
                )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                explain(
                    "A instalação do Ollama demorou demais.",
                    severe=True,
                    app_will="O DroidNote interrompeu a espera e apagou o instalador temporário.",
                    user_can="Verifique a internet e tente de novo.",
                )
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(
                explain(
                    "Não deu para baixar o Ollama (rede, proxy ou GitHub bloqueado).",
                    severe=True,
                    app_will="Nenhum instalador foi executado.",
                    user_can="Verifique VPN/firewall ou baixe em https://ollama.com/download.",
                )
            ) from exc
        finally:
            if installer is not None:
                installer.unlink(missing_ok=True)

    def _serve(self, binary: str) -> None:
        subprocess.Popen(
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    async def _pull(self, on_progress: Callable[[int, str], None] | None = None) -> None:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": self.model, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    total = int(payload.get("total") or 0)
                    completed = int(payload.get("completed") or 0)
                    if total:
                        pct = 50 + int(45 * (completed / total))
                        if on_progress:
                            on_progress(min(pct, 95), f"Baixando {self.model}")
        if not await self.has_model():
            raise RuntimeError(
                explain(
                    f"Não deu para terminar o download do modelo {self.model}.",
                    severe=True,
                    app_will="O DroidNote não trata o arquivo incompleto como válido.",
                    user_can="Tente de novo com internet estável. Se o disco encheu, libere espaço.",
                )
            )


def list_disk_ollama_models() -> list[str]:
    found: set[str] = set()
    for models_root in _ollama_models_roots():
        manifests = models_root / "manifests"
        if not manifests.is_dir():
            continue
        try:
            files = manifests.rglob("*")
        except OSError:
            continue
        for path in files:
            if not path.is_file():
                continue
            try:
                parts = path.relative_to(manifests).parts
            except ValueError:
                continue
            if len(parts) < 2:
                continue
            name, tag = parts[-2], parts[-1]
            if not name or not tag or name.startswith(".") or tag.startswith("."):
                continue
            found.add(f"{name}:{tag}")
    return sorted(found)


def _ollama_models_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        roots.append(path)

    env = os.environ.get("OLLAMA_MODELS")
    if env:
        add(Path(env))
    add(Path.home() / ".ollama" / "models")
    return roots


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(
            explain(
                "O arquivo do Ollama veio corrompido ou adulterado.",
                severe=True,
                app_will="O DroidNote não executou o instalador.",
                user_can="Tente de novo. Se repetir, baixe em ollama.com e volte ao aplicativo.",
            )
        )


def _download_installer() -> Path:
    dest = Path(tempfile.gettempdir()) / f"DroidNote-OllamaSetup-{OLLAMA_SETUP_VERSION}.exe"
    timeout = httpx.Timeout(30.0, read=600.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        with client.stream("GET", OLLAMA_SETUP_URL) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
    return dest


def _format_bytes(size: int) -> str:
    if size <= 0:
        return ""
    value = float(size)
    units = ("B", "KB", "MB", "GB")
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    unit = units[index]
    if unit in {"B", "KB"}:
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"
