"""Sobe a versão do produto em todos os arquivos que precisam andar juntos.

Uso: python installer/bump_version.py patch|minor|major
Imprime a versão nova. No GitHub Actions também grava `version=` em GITHUB_OUTPUT.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = r"\d+\.\d+\.\d+"

# (arquivo, padrão com o prefixo no grupo 1, quantas vezes precisa casar)
TARGETS = [
    ("backend/app/__init__.py", rf'(__version__ = "){SEMVER}', 1),
    ("backend/pyproject.toml", rf'(?m)(^version = "){SEMVER}', 1),
    ("desktop/package.json", rf'(?m)(^  "version": "){SEMVER}', 1),
    ("desktop/package-lock.json", rf'("name": "droidnote-desktop",\s*"version": "){SEMVER}', 2),
    ("desktop/src-tauri/tauri.conf.json", rf'(?m)(^  "version": "){SEMVER}', 1),
    ("desktop/src-tauri/Cargo.toml", rf'(?m)(^version = "){SEMVER}', 1),
    ("desktop/src-tauri/Cargo.lock", rf'(name = "droidnote"\r?\nversion = "){SEMVER}', 1),
    ("desktop/src/pages/AboutPage.tsx", rf'(useState\("){SEMVER}', 1),
]


def current_version() -> str:
    conf = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    return str(conf["version"])


def next_version(current: str, part: str) -> str:
    major, minor, patch = (int(item) for item in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if part not in {"patch", "minor", "major"}:
        raise SystemExit(f"parte inválida: {part}")
    version = next_version(current_version(), part)
    for relative, pattern, expected in TARGETS:
        path = ROOT / relative
        with path.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        updated, count = re.subn(pattern, lambda match: match.group(1) + version, text)
        if count != expected:
            raise SystemExit(f"{relative}: esperava {expected} versão, achei {count}")
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={version}\n")
    print(version)


if __name__ == "__main__":
    main()
