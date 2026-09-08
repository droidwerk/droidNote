from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _load_image_class():
    try:
        from PIL import Image
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"], stdout=subprocess.DEVNULL)
        from PIL import Image
    return Image


def main() -> None:
    Image = _load_image_class()
    source = Path(__file__).resolve().parent / "droidnote-icon.png"
    if not source.exists():
        raise FileNotFoundError(f"Ícone fonte ausente: {source}")
    dest = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri" / "icons"
    dest.mkdir(parents=True, exist_ok=True)
    original = Image.open(source).convert("RGBA")
    for size, name in ((32, "32x32.png"), (128, "128x128.png"), (256, "128x128@2x.png")):
        original.resize((size, size), Image.Resampling.LANCZOS).save(dest / name, "PNG")
    original.save(
        dest / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    )
    leftover = dest / "henry.png"
    leftover.unlink(missing_ok=True)
    print(f"icons written to {dest}")


if __name__ == "__main__":
    main()
