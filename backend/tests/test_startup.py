"""O app instalado confia no DROIDNOTE_READY: depois dele, a porta tem que responder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
VOICE = Path(os.environ.get("APPDATA", "")) / "DroidNote-dev" / "models" / "voice" / "wespeaker_resnet34_lm.onnx"


@pytest.mark.skipif(sys.platform != "win32", reason="sidecar é Windows")
def test_ready_line_only_after_port_accepts_connections(tmp_path) -> None:
    env = {
        **os.environ,
        "DROIDNOTE_DATA_DIR": str(tmp_path),
        "DROIDNOTE_PORT": "0",
        "DROIDNOTE_TOKEN": "startup-test",
        "PYTHONPATH": str(BACKEND),
    }
    if VOICE.exists():
        env["DROIDNOTE_VOICE_MODEL"] = str(VOICE)
    proc = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    try:
        deadline = time.monotonic() + 90
        payload = None
        assert proc.stdout is not None
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            if line.startswith("DROIDNOTE_READY "):
                payload = json.loads(line.split(" ", 1)[1])
                break
        assert payload, "backend não publicou DROIDNOTE_READY"
        # Na hora, sem esperar: é exatamente o que a janela do app faz.
        request = urllib.request.Request(
            f"http://{payload['host']}:{payload['port']}/setup/settings",
            headers={"X-DroidNote-Token": payload["token"]},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
        runtime = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
        assert runtime["port"] == payload["port"]
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_ready_server_waits_for_slow_startup(tmp_path, capsys) -> None:
    """Inicialização lenta (banco grande, antivírus): o anúncio espera, a porta já responde."""
    import asyncio
    import socket
    import threading
    from contextlib import asynccontextmanager

    import uvicorn
    from fastapi import FastAPI

    from app.main import _ReadyServer

    @asynccontextmanager
    async def slow(app):
        await asyncio.sleep(2)
        yield

    application = FastAPI(lifespan=slow)

    @application.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "1"}

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning")
    runtime = tmp_path / "runtime.json"
    server = _ReadyServer(config, {"host": "127.0.0.1", "port": port, "token": "t"}, runtime)
    thread = threading.Thread(target=server.run, daemon=True)
    started = time.monotonic()
    thread.start()
    try:
        while not runtime.exists() and time.monotonic() - started < 20:
            time.sleep(0.02)
        assert runtime.exists()
        assert time.monotonic() - started >= 1.9  # esperou a inicialização terminar
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=5) as response:
            assert response.status == 200
        assert "DROIDNOTE_READY" in capsys.readouterr().out
    finally:
        server.should_exit = True
        thread.join(timeout=10)
