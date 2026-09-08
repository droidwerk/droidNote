$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Desktop = Join-Path $Root "desktop"
$SidecarSrc = Join-Path $Backend "dist\droidnote-backend"
$SidecarDestDir = Join-Path $Desktop "src-tauri\resources\droidnote-backend"
$TimestampUrl = "http://timestamp.digicert.com"

function Sign-IfConfigured([string]$Path) {
    $thumb = $env:DROIDNOTE_CERT_THUMBPRINT
    if (-not $thumb) {
        return
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Arquivo para assinar não existe: $Path"
    }
    $signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if (-not $signtool) {
        throw "DROIDNOTE_CERT_THUMBPRINT definido, mas signtool.exe não está no PATH. Instale o Windows SDK."
    }
    & signtool.exe sign /fd SHA256 /td SHA256 /tr $TimestampUrl /sha1 $thumb $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao assinar $Path"
    }
    Write-Host "Assinado: $Path"
}

if (-not $env:DROIDNOTE_CERT_THUMBPRINT) {
    Write-Warning "Instalador sairá SEM Authenticode. Para lançamento público: certificado EV e DROIDNOTE_CERT_THUMBPRINT."
}

$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path (Join-Path $CargoBin "cargo.exe")) {
    $env:Path = "$CargoBin;$env:Path"
} else {
    throw "Rust/Cargo não encontrado em $CargoBin. Instale o rustup e abra um terminal novo."
}

# O .exe solto na raiz não leva o backend. Só o Setup instala o app completo.
$LooseApp = Join-Path $Root "DroidNote.exe"
if (Test-Path $LooseApp) {
    Remove-Item -Force $LooseApp
    Write-Host "Removido DroidNote.exe solto (não é o entregável)."
}

python "$PSScriptRoot\generate_icons.py"

Push-Location $Backend
python -m pip install -e ".[dev]"
python -m PyInstaller --noconfirm --clean sidecar.spec
Pop-Location

$SidecarExe = Join-Path $SidecarSrc "droidnote-backend.exe"
if (-not (Test-Path $SidecarExe)) {
    throw "PyInstaller não gerou $SidecarExe"
}
Sign-IfConfigured $SidecarExe

if (Test-Path $SidecarDestDir) { Remove-Item -Recurse -Force $SidecarDestDir }
New-Item -ItemType Directory -Force -Path (Split-Path $SidecarDestDir) | Out-Null
Copy-Item -Recurse $SidecarSrc $SidecarDestDir
$BundledSidecar = Join-Path $SidecarDestDir "droidnote-backend.exe"
if (Test-Path $BundledSidecar) {
    Sign-IfConfigured $BundledSidecar
}

Push-Location $Desktop
npm install
$bundleOk = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    npm run tauri build
    if ($LASTEXITCODE -eq 0) {
        $bundleOk = $true
        break
    }
    Write-Host "Tentativa $attempt de bundle falhou (arquivo em uso?). Aguardando 8s..."
    Start-Sleep -Seconds 8
}
if (-not $bundleOk) {
    Pop-Location
    throw "tauri build falhou após 3 tentativas"
}
Pop-Location

$ReleaseExe = Join-Path $Desktop "src-tauri\target\release\DroidNote.exe"
if (Test-Path $ReleaseExe) {
    Sign-IfConfigured $ReleaseExe
}

$NsisDir = Join-Path $Desktop "src-tauri\target\release\bundle\nsis"
if (-not (Test-Path $NsisDir)) {
    throw "NSIS não gerou pasta em $NsisDir"
}
$Built = Get-ChildItem -Path $NsisDir -Filter "*setup.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Built) {
    throw "NSIS não gerou o setup.exe em $NsisDir"
}
Sign-IfConfigured $Built.FullName
$Dest = Join-Path $Root "DroidNote-Setup.exe"
Copy-Item -Force $Built.FullName $Dest
Sign-IfConfigured $Dest
if (Test-Path $LooseApp) { Remove-Item -Force $LooseApp }
Write-Host ""
Write-Host "Instalador: $Dest"
Write-Host "Rode esse Setup neste PC (sem admin)."
Write-Host "App: $env:LOCALAPPDATA\DroidNote"
Write-Host "Atalho: Area de Trabalho e Menu Iniciar\DroidNote"
try { Invoke-Item -LiteralPath $Root } catch {}
