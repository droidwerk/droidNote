# Third-party notices

DroidNote is built on open-source software and ships or downloads third-party components. This page lists them with their licences so the attribution each licence asks for travels with the product. All of them are compatible with the AGPL-3.0 under which DroidNote itself is released. Versions are those pinned in `backend/pyproject.toml`, `desktop/package.json` and `desktop/src-tauri/Cargo.toml`.

## Shipped inside the installer

### Backend (Python sidecar)

| Component | Licence | Source |
| --- | --- | --- |
| Python | PSF License | https://www.python.org |
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| Pydantic, pydantic-settings | MIT | https://github.com/pydantic/pydantic |
| aiosqlite | MIT | https://github.com/omnilib/aiosqlite |
| NumPy | BSD-3-Clause | https://github.com/numpy/numpy |
| HTTPX | BSD-3-Clause | https://github.com/encode/httpx |
| SoundCard | BSD-3-Clause | https://github.com/bastibe/SoundCard |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| ReportLab (open-source edition) | BSD-3-Clause | https://www.reportlab.com |
| python-docx | MIT | https://github.com/python-openxml/python-docx |
| python-dateutil | Apache-2.0 / BSD-3-Clause | https://github.com/dateutil/dateutil |
| tzdata | Apache-2.0 | https://github.com/python/tzdata |
| LangChain (core, community, text-splitters) | MIT | https://github.com/langchain-ai/langchain |
| pypdf | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| docx2txt | MIT | https://github.com/ankushshah89/python-docx2txt |
| openpyxl | MIT | https://foss.heptapod.net/openpyxl/openpyxl |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| PyInstaller (build tool; its bootloader is embedded in the sidecar) | GPL-2.0-or-later with the bootloader exception | https://github.com/pyinstaller/pyinstaller |

### Desktop shell (Tauri + React)

| Component | Licence | Source |
| --- | --- | --- |
| Tauri and its plugins (shell, dialog, single-instance) | MIT or Apache-2.0 | https://github.com/tauri-apps/tauri |
| serde, serde_json | MIT or Apache-2.0 | https://github.com/serde-rs/serde |
| React, React DOM | MIT | https://github.com/facebook/react |
| Tiptap (react, starter-kit, pm) and ProseMirror | MIT | https://github.com/ueberdosis/tiptap |
| mind-elixir | MIT | https://github.com/SSShooter/mind-elixir-core |
| Microsoft Edge WebView2 Runtime (installed by the bootstrap if missing) | Microsoft WebView2 licence terms | https://developer.microsoft.com/microsoft-edge/webview2/ |

### Models bundled in the installer

| Component | Licence | Source |
| --- | --- | --- |
| WeSpeaker ResNet34-LM speaker embedding model (`wespeaker_resnet34_lm.onnx`) | Apache-2.0 | https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM · https://github.com/wenet-e2e/wespeaker |

## Downloaded on the user's PC when the user chooses them

These are never redistributed by DroidWerk. The setup wizard shows what will be fetched and from where; by downloading, the user accepts the terms of each one.

| Component | Licence / terms | Source |
| --- | --- | --- |
| Ollama (local LLM server) | MIT | https://github.com/ollama/ollama |
| Whisper models for faster-whisper (Systran conversions of OpenAI Whisper) | MIT | https://huggingface.co/Systran |
| Google Gemma 4 (`gemma4:*`) and Gemma 3 | Gemma Terms of Use | https://ai.google.dev/gemma/terms |
| Alibaba Qwen 3.6 / Qwen 3 / Qwen 2.5 | Apache-2.0 | https://github.com/QwenLM |
| Meta Llama 3.1 | Llama 3.1 Community License | https://www.llama.com/llama3_1/license/ |

## Services used only with the user's own key

| Service | Terms |
| --- | --- |
| OpenAI API (transcription and language models) | https://openai.com/policies |

## Fonts

The PDF and Word exports reference Segoe UI and Consolas, which are part of the user's Windows installation. DroidNote does not ship font files.

---

If a component is missing from this list, or a licence is wrong, please open an issue; keeping this page accurate is part of every release.
