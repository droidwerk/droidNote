$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TimestampUrl = "http://timestamp.digicert.com"

# O macro generate_context! do Tauri grava CARGO_MANIFEST_DIR dentro do binário, e
# o remap de caminhos do rustc não alcança isso: é variável de ambiente lida em
# tempo de compilação. Se o repositório mora em C:\Users\<alguém>, esse nome vai
# junto para o PC de todo mundo que instalar. Compilar através de uma junção num
# caminho sem dado pessoal resolve sem copiar o projeto (a junção aponta para os
# mesmos arquivos, então node_modules e target continuam sendo reaproveitados).
function Get-NeutralBuildRoot([string]$Target) {
    $link = Join-Path $env:PUBLIC "droidnote-build"
    if (Test-Path -LiteralPath $link) {
        $item = Get-Item -LiteralPath $link -Force
        if ($item.LinkType -ne "Junction") {
            Write-Warning "$link existe e não é junção. Compilando pelo caminho original."
            return $Target
        }
        if (($item.Target | Select-Object -First 1) -eq $Target) {
            return $link
        }
        cmd /c rmdir "$link" | Out-Null
    }
    cmd /c mklink /J "$link" "$Target" | Out-Null
    if (Test-Path -LiteralPath (Join-Path $link "desktop\src-tauri\Cargo.toml")) {
        Write-Host "Compilando por $link (mantém o caminho desta máquina fora do binário)."
        return $link
    }
    Write-Warning "Não foi possível criar a junção em $link. O binário levará o caminho desta máquina."
    return $Target
}

$BuildRoot = Get-NeutralBuildRoot $Root
$Backend = Join-Path $BuildRoot "backend"
$Desktop = Join-Path $BuildRoot "desktop"
$SidecarSrc = Join-Path $Backend "dist\droidnote-backend"
$SidecarDestDir = Join-Path $Desktop "src-tauri\resources\droidnote-backend"

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

# O rustc grava o caminho de cada arquivo compilado nas mensagens de panic, então
# o binário entregue ao usuário carregaria "C:\Users\<quem compilou>\.cargo\...".
# Os prefixos são calculados aqui para não haver nome de usuário no repositório.
# CARGO_ENCODED_RUSTFLAGS (separador 0x1F) em vez de RUSTFLAGS: este último quebra
# em caminhos com espaço.
$CargoHome = if ($env:CARGO_HOME) { $env:CARGO_HOME } else { Join-Path $env:USERPROFILE ".cargo" }
$RustUp = if ($env:RUSTUP_HOME) { $env:RUSTUP_HOME } else { Join-Path $env:USERPROFILE ".rustup" }
$Sep = [char]0x1F
$env:CARGO_ENCODED_RUSTFLAGS = @(
    "--remap-path-prefix=$CargoHome=/cargo",
    "--remap-path-prefix=$RustUp=/rustup",
    "--remap-path-prefix=$BuildRoot=/droidnote",
    "--remap-path-prefix=$Root=/droidnote"
) -join $Sep

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

# O rollup recusa a junção (compara o caminho canônico com o caminho do projeto e
# acha que index.html está fora da raiz), então o frontend compila pelo caminho
# real e o tauri build só empacota o que já está em desktop/dist.
Push-Location (Join-Path $Root "desktop")
npm install
npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    throw "npm run build falhou"
}
Pop-Location

$SkipBefore = Join-Path $env:TEMP "droidnote-skip-before-build.json"
'{ "build": { "beforeBuildCommand": "" } }' | Set-Content -LiteralPath $SkipBefore -Encoding utf8

Push-Location $Desktop
$bundleOk = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    npm run tauri -- build --config $SkipBefore
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
