<#
.SYNOPSIS
    Installs the latest DroidNote release on this PC without any clicks.

.DESCRIPTION
    One line, in PowerShell (no administrator rights needed):

        irm https://github.com/droidwerk/droidNote/releases/latest/download/install.ps1 | iex

    What it does, in order:
      1. Downloads the latest DroidNote-Setup.exe and SHA256SUMS.txt from the GitHub release.
      2. Checks the installer's SHA-256 against the published sum; stops if it differs.
      3. Runs the installer silently (per user, into %LOCALAPPDATA%\DroidNote).
      4. Leaves a note for the app's first start so it skips the wizard and prepares the
         local models the hardware recommends (nothing leaves the PC).
      5. Opens DroidNote.

    Options, as environment variables set before the command:
      DROIDNOTE_NO_LAUNCH=1   install but do not open the app
      DROIDNOTE_AGENT=name    which assistant ran this (recorded locally only, e.g. claude-code)
      DROIDNOTE_LANGUAGE=pt   app language (pt, en, es, fr, de, it, ru); default: Windows language

    Works with Windows 10/11 x64. Uninstall later from Settings > Apps > DroidNote.
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$Repo = "droidwerk/droidNote"
$Base = "https://github.com/$Repo/releases/latest/download"
$InstallerName = "DroidNote-Setup.exe"
$SumsName = "SHA256SUMS.txt"
$AppExe = Join-Path $env:LOCALAPPDATA "DroidNote\DroidNote.exe"
$DataDir = Join-Path $env:APPDATA "DroidNote"

function Step([string] $Text) { Write-Host "  > $Text" }
function Fail([string] $Text) { Write-Host ""; Write-Host "DroidNote was not installed: $Text" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "DroidNote installer" -ForegroundColor Cyan
Write-Host "Local meeting transcription, minutes and memory, on this PC." -ForegroundColor DarkGray
Write-Host ""

if ($env:OS -ne "Windows_NT") { Fail "DroidNote runs on Windows 10/11." }
if (-not [Environment]::Is64BitOperatingSystem) { Fail "DroidNote needs 64-bit Windows." }

$Temp = Join-Path $env:TEMP ("droidnote-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
$Installer = Join-Path $Temp $InstallerName
$Sums = Join-Path $Temp $SumsName

try {
    $version = "latest"
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "DroidNote-install" } -TimeoutSec 20
        if ($release.tag_name) { $version = [string] $release.tag_name }
    } catch { }

    Step "Downloading DroidNote $version"
    Invoke-WebRequest -Uri "$Base/$InstallerName" -OutFile $Installer -UseBasicParsing
    Invoke-WebRequest -Uri "$Base/$SumsName" -OutFile $Sums -UseBasicParsing

    Step "Checking the installer's SHA-256"
    $expected = $null
    foreach ($line in Get-Content $Sums) {
        $parts = $line.Trim() -split "\s+"
        if ($parts.Length -ge 2 -and $parts[-1].TrimStart("*") -eq $InstallerName) { $expected = $parts[0].ToLower() }
    }
    if (-not $expected) { Fail "SHA256SUMS.txt in the release has no entry for $InstallerName." }
    $actual = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower()
    if ($actual -ne $expected) { Fail "the downloaded installer does not match the published checksum. Nothing was run." }
    Unblock-File -Path $Installer

    Step "Installing (silent, no administrator rights)"
    $process = Start-Process -FilePath $Installer -ArgumentList "/S" -Wait -PassThru
    if ($process.ExitCode -ne 0) { Fail "the installer exited with code $($process.ExitCode)." }
    if (-not (Test-Path $AppExe)) { Fail "the installer finished but $AppExe is missing." }

    Step "Preparing the first start"
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $language = $env:DROIDNOTE_LANGUAGE
    if (-not $language) { try { $language = (Get-Culture).TwoLetterISOLanguageName } catch { $language = "en" } }
    $agent = $env:DROIDNOTE_AGENT
    if (-not $agent) { $agent = "install.ps1" }
    $marker = @{
        provider   = "neste_pc"
        language   = $language.ToLower()
        agent      = $agent
        version    = $version
        created_at = (Get-Date).ToString("o")
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText((Join-Path $DataDir "unattended.json"), $marker, (New-Object Text.UTF8Encoding $false))
}
finally {
    Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "DroidNote installed." -ForegroundColor Green
Write-Host "  App:  $AppExe"
Write-Host "  Data: $DataDir"
Write-Host ""
Write-Host "On first start DroidNote prepares the local models (Whisper and a language model, a few GB)."
Write-Host "Everything stays on this PC. To use the OpenAI API instead, change it in Preferences."
Write-Host "Uninstall from Settings > Apps > DroidNote."

if ($env:DROIDNOTE_NO_LAUNCH -ne "1") {
    Step "Opening DroidNote"
    Start-Process -FilePath $AppExe | Out-Null
}
