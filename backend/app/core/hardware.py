from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from pathlib import Path

from app.core.logging import get_logger

log = get_logger("hardware")

DISK_MARGIN = 1.2
OLLAMA_INSTALLER_GB = 1.5
WHISPER_DOWNLOAD_GB: dict[str, float] = {
    "tiny": 0.08,
    "base": 0.15,
    "small": 0.5,
    "medium": 1.5,
    "large-v3": 3.1,
    "large-v3-turbo": 1.6,
    "distil-large-v3": 1.5,
}
OLLAMA_DOWNLOAD_GB: dict[str, float] = {
    "qwen2.5:3b": 2.0,
    "qwen3:4b": 2.5,
    "qwen3:8b": 5.2,
    "llama3.1:8b": 4.9,
    "gemma3:12b": 8.1,
}
VRAM_TURBO_GB = 6.0


def total_ram_gb() -> float:
    """RAM total da máquina, em GB. Zero quando não é possível descobrir."""
    return _windows_ram_gb(available=False) if os.name == "nt" else _posix_ram_gb()


def available_ram_gb() -> float:
    """RAM livre agora. Zero quando não é possível descobrir."""
    return _windows_ram_gb(available=True) if os.name == "nt" else _posix_ram_gb()


def _posix_ram_gb() -> float:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return 0.0
    return pages * page_size / 1024**3


def _windows_ram_gb(*, available: bool) -> float:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0.0
    value = status.ullAvailPhys if available else status.ullTotalPhys
    return value / 1024**3


def free_disk_gb(path: Path | None = None) -> float:
    """Espaço livre no volume de `path`, em GB. Zero se não der para medir."""
    target = Path(path) if path else Path.cwd()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = Path(target.anchor) if target.anchor else Path.cwd()
    if os.name == "nt":
        return _windows_free_disk_gb(target)
    try:
        return shutil.disk_usage(target).free / 1024**3
    except OSError:
        return 0.0


def _windows_free_disk_gb(path: Path) -> float:
    free = ctypes.c_ulonglong(0)
    ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        str(path),
        None,
        None,
        ctypes.byref(free),
    )
    if not ok:
        return 0.0
    return free.value / 1024**3


def vram_gb() -> float:
    """VRAM da primeira GPU NVIDIA, em GB. Zero se não houver nvidia-smi."""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    if completed.returncode != 0:
        return 0.0
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        return 0.0
    try:
        return float(line[0].strip()) / 1024.0
    except ValueError:
        return 0.0


def estimate_download_gb(
    *,
    whisper_id: str | None,
    note_id: str | None,
    need_installer: bool,
    whisper_installed: bool,
    note_installed: bool,
) -> float:
    total = 0.0
    if need_installer:
        total += OLLAMA_INSTALLER_GB
    if whisper_id and not whisper_installed:
        total += WHISPER_DOWNLOAD_GB.get(whisper_id, 2.0)
    if note_id and not note_installed:
        total += OLLAMA_DOWNLOAD_GB.get(note_id, 5.0)
    return total


def required_disk_gb(download_gb: float) -> float:
    return download_gb * DISK_MARGIN


def disk_has_room(path: Path, download_gb: float) -> tuple[bool, float, float]:
    """(ok, livre, necessário com margem). Sem medida (livre=0) não bloqueia."""
    needed = required_disk_gb(download_gb)
    free = free_disk_gb(path)
    if download_gb <= 0:
        return True, free, needed
    if free <= 0:
        return True, free, needed
    return free >= needed, free, needed


def suggest_note_model(ram_gb: float | None = None) -> str:
    """Modelo local de nota que a máquina aguenta sem travar."""
    ram = available_ram_gb() if ram_gb is None else ram_gb
    if ram >= 24:
        return "gemma3:12b"
    if ram >= 16:
        return "qwen3:8b"
    if ram >= 8:
        return "qwen3:4b"
    if ram > 0:
        return "qwen2.5:3b"
    return "qwen3:4b"


def suggest_whisper_model(
    ram_gb: float | None = None,
    *,
    cuda: bool | None = None,
    vram: float | None = None,
) -> str:
    del ram_gb
    has_gpu = cuda_usable() if cuda is None else cuda
    if not has_gpu:
        return "small"
    vram_val = vram_gb() if vram is None else vram
    if vram_val >= VRAM_TURBO_GB:
        return "large-v3-turbo"
    return "small"


def cuda_usable() -> bool:
    try:
        from app.infrastructure.asr.whisper_engine import _cuda_usable

        return _cuda_usable()
    except Exception:
        return False
