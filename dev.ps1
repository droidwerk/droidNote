$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Desktop = Join-Path $Root "desktop"
$Token = "dev-token"
$Port = 8765
$FrontPort = 1420
$Url = "http://127.0.0.1:$Port"

function Stop-ListenersOnPort([int]$ListenPort) {
    $pids = @()
    try {
        $pids = @(
            Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {
        $lines = netstat -ano | Select-String ":$ListenPort\s"
        foreach ($line in $lines) {
            $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
            if ($parts.Count -ge 5 -and $parts[-1] -match "^\d+$") {
                $pids += [int]$parts[-1]
            }
        }
        $pids = $pids | Select-Object -Unique
    }
    foreach ($procId in $pids) {
        if ($procId -and $procId -ne $PID -and $procId -ne 0) {
            Write-Host "Encerrando PID $procId na porta $ListenPort"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-DroidNoteApps {
    Get-Process -Name "droidnote", "DroidNote" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path (Join-Path $CargoBin "cargo.exe")) {
    $env:Path = "$CargoBin;$env:Path"
}

Write-Host "Fechando backend/front antigos, se existirem..."
Stop-DroidNoteApps
Stop-ListenersOnPort $Port
Stop-ListenersOnPort $FrontPort
Start-Sleep -Seconds 1

$env:DROIDNOTE_TOKEN = $Token
$env:DROIDNOTE_PORT = "$Port"
$env:DROIDNOTE_URL = $Url
$env:DROIDNOTE_EXTERNAL_BACKEND = "1"
$devData = Join-Path $env:APPDATA "DroidNote-dev"
$env:DROIDNOTE_DATA_DIR = $devData

Write-Host "Subindo backend com reload em $Url ..."
$backendCmd = @"
`$env:DROIDNOTE_TOKEN='$Token'
`$env:DROIDNOTE_PORT='$Port'
`$env:DROIDNOTE_DATA_DIR='$devData'
Set-Location -LiteralPath '$Backend'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port --reload-dir app
"@
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCmd) | Out-Null

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $null = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 2
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    throw "Backend nao respondeu em $Url/health. Veja a janela do Python."
}

Write-Host "Backend ok. Abrindo DroidNote (Tauri)."
Write-Host "Ctrl+C nesta janela para o front. Feche a janela do Python para o backend."
Set-Location -LiteralPath $Desktop
npm run tauri dev
