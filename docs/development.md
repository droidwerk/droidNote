# Desenvolvimento

## Requisitos

- Windows 10/11 x64
- Python 3.11 ou superior (`python` no PATH)
- Node.js 20+ (npm)
- Rust via rustup (`%USERPROFILE%\.cargo\bin` no PATH)

Perfil de dados em desenvolvimento: `%APPDATA%\DroidNote-dev`. O app instalado usa `%APPDATA%\DroidNote`. Os dois não se misturam.

## Correr em dev

Na raiz do repositório:

```powershell
.\dev.ps1
```

Isto:

1. Fecha instâncias antigas do DroidNote e liberta as portas `8765` e `1420`.
2. Sobe o FastAPI com reload em `http://127.0.0.1:8765` (`DROIDNOTE_TOKEN=dev-token`).
3. Sobe o Tauri/Vite com `DROIDNOTE_EXTERNAL_BACKEND=1`, para a janela usar esse backend em vez de lançar o sidecar.

O backend responde em `GET /health` quando está pronto.

### Manual

```powershell
# terminal 1
cd backend
$env:DROIDNOTE_TOKEN = "dev-token"
$env:DROIDNOTE_PORT = "8765"
$env:DROIDNOTE_DATA_DIR = "$env:APPDATA\DroidNote-dev"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765 --reload-dir app

# terminal 2
cd desktop
$env:DROIDNOTE_EXTERNAL_BACKEND = "1"
$env:DROIDNOTE_URL = "http://127.0.0.1:8765"
$env:DROIDNOTE_TOKEN = "dev-token"
npm install
npm run tauri dev
```

## Testes

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest
```

## Build do instalador

```powershell
.\installer\build-windows.ps1
```

Passos: PyInstaller do sidecar → copia para `desktop/src-tauri/resources/droidnote-backend` → `npm run tauri build` → NSIS. O Setup sai em `desktop/src-tauri/target/release/bundle/nsis/` e é copiado para `DroidNote-Setup.exe` na raiz (ficheiro ignorado pelo git).

Assinatura Authenticode só corre se `DROIDNOTE_CERT_THUMBPRINT` estiver definido. Sem isso o Windows SmartScreen avisa na primeira execução.

O instalador precisa que `droidnote.exe` e `droidnote-backend.exe` não estejam a correr. Os hooks NSIS já tentam matar os dois.

## Versão

A versão do produto está nestes sítios, e devem avançar juntos num release:

- `backend/app/__init__.py`
- `backend/pyproject.toml`
- `desktop/package.json` e `package-lock.json`
- `desktop/src-tauri/tauri.conf.json`
- `desktop/src-tauri/Cargo.toml` e `Cargo.lock`
- fallback em `desktop/src/pages/AboutPage.tsx`

Tag git: `vMAJOR.MINOR.PATCH`. Assets da release: `DroidNote-Setup.exe` e `DroidNote_<versão>_x64-setup.exe`.

## Layout do repo

| Pasta | Conteúdo |
| --- | --- |
| `backend/` | FastAPI, testes, `sidecar.spec` |
| `desktop/` | UI React e crate Tauri (`src-tauri/`) |
| `installer/` | `build-windows.ps1`, ícones |
| `docs/` | Arquitetura e este guia |
