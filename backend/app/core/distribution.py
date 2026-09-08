"""Commercial distribution policy.

Signing: EV Authenticode + RFC 3161 timestamp. The Windows build signs
Setup, DroidNote.exe and droidnote-backend.exe when DROIDNOTE_CERT_THUMBPRINT
is set. Until a certificate is configured, SmartScreen will warn on first run.

Ollama: option C — pin a GitHub release, stream the installer to disk, verify
SHA-256 from the official asset digest, then run it. Never follow /latest.
Do not bundle the ~1 GB installer inside DroidNote-Setup.

Updater: deferred. Reinstall via NSIS must keep %APPDATA%\\DroidNote.
Do not enable tauri-plugin-updater until there is a signed update endpoint.

Secrets: Windows DPAPI for asr_api_key. Legacy plaintext is migrated on read.
"""

from __future__ import annotations

OLLAMA_SETUP_VERSION = "0.33.3"
OLLAMA_SETUP_URL = (
    f"https://github.com/ollama/ollama/releases/download/v{OLLAMA_SETUP_VERSION}/OllamaSetup.exe"
)
# GitHub release asset digest for OllamaSetup.exe on v0.33.3.
OLLAMA_SETUP_SHA256 = "32cdcb1da477bc7fffbf1c1cdeeb99b1db003af094db56dd3c156abd04d34f8e"

TIMESTAMP_URL = "http://timestamp.digicert.com"
SIGNING_ENV = "DROIDNOTE_CERT_THUMBPRINT"
