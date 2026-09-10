# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules("uvicorn") + collect_submodules("fastapi") + collect_submodules("soundcard")
try:
    hidden += collect_submodules("faster_whisper")
    hidden += collect_submodules("ctranslate2")
    hidden += collect_submodules("huggingface_hub")
except Exception:
    pass

datas = []
try:
    datas += collect_data_files("faster_whisper")
except Exception:
    pass

a = Analysis(
    ["app/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden + [
        "app",
        "aiosqlite",
        "numpy",
        "httpx",
        "pydantic",
        "pydantic_settings",
        "anyio",
        "starlette",
        "ctranslate2",
        "huggingface_hub",
        "certifi",
        "tokenizers",
        "onnxruntime",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "ipykernel",
        "jupyter",
        "notebook",
        "jedi",
        "parso",
        "prompt_toolkit",
        "tornado",
        "PIL",
        "Pillow",
        "zmq",
        "pytest",
        "pygments",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="droidnote-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="droidnote-backend",
)
