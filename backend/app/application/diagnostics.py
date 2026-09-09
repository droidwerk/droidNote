from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app import __version__
from app.core.config import Settings
from app.core.hardware import available_ram_gb, cuda_usable, free_disk_gb, total_ram_gb, vram_gb

_TOKEN = re.compile(r"(token|api[_-]?key)([\"'\s:=]+)([^\s\"']+)", re.IGNORECASE)


def write_diagnostic_zip(settings: Settings) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dest = settings.data_dir / "logs" / f"DroidNote-diagnostico-{stamp}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "app": "DroidNote",
        "version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "ram_gb": round(total_ram_gb(), 2),
        "ram_available_gb": round(available_ram_gb(), 2),
        "vram_gb": round(vram_gb(), 2),
        "cuda": cuda_usable(),
        "free_disk_gb": round(free_disk_gb(settings.data_dir), 2),
        "provider": settings.provider,
        "whisper_model": settings.whisper_model,
        "ollama_model": settings.ollama_model,
        "host": settings.host,
        "packaged": bool(getattr(sys, "frozen", False)),
    }
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
        for name in ("backend.log", "boot-error.log"):
            path = settings.data_dir / "logs" / name
            if not path.is_file():
                path = settings.data_dir / name
            if path.is_file():
                archive.writestr(name, _redact(path.read_text(encoding="utf-8", errors="replace")))
    return dest


def _redact(text: str) -> str:
    return _TOKEN.sub(r"\1\2[redacted]", text)
