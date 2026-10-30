<#
.SYNOPSIS
    Installs the latest DroidNote release on this PC without any clicks.

.DESCRIPTION
    One line, in PowerShell (no administrator rights needed):

        irm https://github.com/droidwerk/droidNote/releases/latest/download/install.ps1 | iex

    What it does, in order:
      1. Downloads the latest DroidNote-Setup.exe and SHA256SUMS.txt from the GitHub release.
      2. Checks the installer's SHA-256 against the published sum; stops if it differs.
      3. Runs the installer silently (per user, into %LOCALAPPDATA%\DroidNote), with the same
         Start menu and desktop shortcuts and the same Settings > Apps entry as the manual Setup.
      4. Leaves a note for the app's first start so it skips the wizard and prepares the
         local models the hardware recommends (nothing leaves the PC).
      5. Opens DroidNote.

    When it runs inside a packaged (MSIX) app, such as the Claude desktop app, Windows keeps
    whatever that app's child processes write to %LOCALAPPDATA%, %APPDATA% and HKCU\Software in
    a private copy for the app. An install made from there runs, but has no Start menu entry and
    no Settings > Apps entry. So in that case steps 3-5 run from a small visible .cmd file next to
    the downloaded installer, opened through Explorer the same way a double click would.

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

# Folder name of the MSIX package whose private copy catches this process's writes to
# %LOCALAPPDATA%, or $null when they reach the real profile. The package identity API is not
# enough: the Claude desktop app starts its terminals without identity but still redirected.
function Get-PackageFamily {
    $name = "droidnote-probe-" + [guid]::NewGuid().ToString("N")
    $probe = Join-Path $env:LOCALAPPDATA $name
    try {
        [IO.File]::WriteAllText($probe, "")
        $packages = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Packages") -Directory -ErrorAction SilentlyContinue
        foreach ($package in $packages) {
            if (Test-Path -LiteralPath (Join-Path $package.FullName "LocalCache\Local\$name")) { return $package.Name }
        }
        return $null
    } catch {
        return $null
    } finally {
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    }
}

function Get-FirstStartNote([string] $Version) {
    $language = $env:DROIDNOTE_LANGUAGE
    if (-not $language) { try { $language = (Get-Culture).TwoLetterISOLanguageName } catch { $language = "en" } }
    $agent = $env:DROIDNOTE_AGENT
    if (-not $agent) { $agent = "install.ps1" }
    return @{
        provider   = "neste_pc"
        language   = $language.ToLower()
        agent      = $agent
        version    = $Version
        created_at = (Get-Date).ToString("o")
    } | ConvertTo-Json -Compress
}

# Inside a package, Explorer starts the .cmd outside it, so the installer and the note reach the
# real profile. The .cmd and the installer live in Downloads, which the package does not redirect.
function Install-OutsidePackage([string] $Family, [string] $Work, [string] $Installer, [string] $Version) {
    Step "This terminal runs inside the app package $Family"
    Step "Installing through Explorer, so DroidNote gets its Start menu entry and appears in Settings > Apps"

    # A previous install from inside this package only exists in its private copy and would hide
    # the real one from this side. The program files can go; the data folder (%APPDATA%) stays.
    $ghost = Join-Path $env:LOCALAPPDATA "Packages\$Family\LocalCache\Local\DroidNote"
    if (Test-Path $ghost) {
        Remove-Item -Recurse -Force $ghost -ErrorAction SilentlyContinue
        Step "Removed the earlier copy that was installed inside $Family"
    }

    [IO.File]::WriteAllText((Join-Path $Work "unattended.json"), (Get-FirstStartNote $Version), (New-Object Text.UTF8Encoding $false))
    $started = Join-Path $Work "started.txt"
    $done = Join-Path $Work "done.txt"
    $cmd = Join-Path $Work "install.cmd"
    # Redirections go first: "echo 0> file" would read "0>" as a handle number and write nothing.
    $lines = @(
        "@echo off",
        "if exist `"%~dp0started.txt`" exit /b",
        ">`"%~dp0started.txt`" echo 1",
        "title DroidNote install",
        "echo Installing DroidNote, this window closes by itself.",
        "`"%~dp0$InstallerName`" /S",
        "set code=%errorlevel%",
        "if not `"%code%`"==`"0`" goto end",
        "if not exist `"%APPDATA%\DroidNote`" mkdir `"%APPDATA%\DroidNote`"",
        "copy /y `"%~dp0unattended.json`" `"%APPDATA%\DroidNote\unattended.json`" >nul",
        ":end",
        ">`"%~dp0done.txt`" echo %code%"
    )
    [IO.File]::WriteAllText($cmd, ($lines -join "`r`n") + "`r`n", (New-Object Text.ASCIIEncoding))

    Step "Installing (silent, no administrator rights)"
    # Explorer sometimes drops the first request; the .cmd ignores a second start.
    for ($try = 0; $try -lt 3 -and -not (Test-Path $started); $try++) {
        Start-Process -FilePath "explorer.exe" -ArgumentList "`"$cmd`""
        for ($wait = 0; $wait -lt 15 -and -not (Test-Path $started); $wait++) { Start-Sleep -Seconds 1 }
    }
    if (-not (Test-Path $started)) { Fail "Windows did not start the install window. Run $InstallerName from https://github.com/$Repo/releases/latest by hand." }
    $deadline = (Get-Date).AddMinutes(30)
    while (-not (Test-Path $done) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    if (-not (Test-Path $done)) { Fail "the install window did not finish within 30 minutes. Run $InstallerName from https://github.com/$Repo/releases/latest by hand." }
    Start-Sleep -Milliseconds 500
    $code = "$(Get-Content $done -Raw)".Trim()
    if ($code -ne "0") { Fail "the installer exited with code $code." }
    if (-not (Test-Path $AppExe)) { Fail "the installer finished but $AppExe is missing." }
}

Write-Host ""
Write-Host "DroidNote installer" -ForegroundColor Cyan
Write-Host "Local meeting transcription, minutes and memory, on this PC." -ForegroundColor DarkGray
Write-Host ""

if ($env:OS -ne "Windows_NT") { Fail "DroidNote runs on Windows 10/11." }
if (-not [Environment]::Is64BitOperatingSystem) { Fail "DroidNote needs 64-bit Windows." }

$Family = Get-PackageFamily
if ($Family) {
    # %TEMP% is under %LOCALAPPDATA%, so a process outside the package would not see it.
    $downloads = Join-Path $env:USERPROFILE "Downloads"
    if (-not (Test-Path $downloads)) { $downloads = $env:USERPROFILE }
    $Work = Join-Path $downloads ("droidnote-install-" + [guid]::NewGuid().ToString("N"))
} else {
    $Work = Join-Path $env:TEMP ("droidnote-install-" + [guid]::NewGuid().ToString("N"))
}
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$Installer = Join-Path $Work $InstallerName
$Sums = Join-Path $Work $SumsName

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

    if ($Family) {
        Install-OutsidePackage $Family $Work $Installer $version
    } else {
        Step "Installing (silent, no administrator rights)"
        $process = Start-Process -FilePath $Installer -ArgumentList "/S" -Wait -PassThru
        if ($process.ExitCode -ne 0) { Fail "the installer exited with code $($process.ExitCode)." }
        if (-not (Test-Path $AppExe)) { Fail "the installer finished but $AppExe is missing." }

        Step "Preparing the first start"
        New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
        [IO.File]::WriteAllText((Join-Path $DataDir "unattended.json"), (Get-FirstStartNote $version), (New-Object Text.UTF8Encoding $false))
    }
}
finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "DroidNote installed." -ForegroundColor Green
Write-Host "  App:  $AppExe"
Write-Host "  Data: $DataDir"
Write-Host ""
Write-Host "On first start DroidNote prepares the local models (Whisper and a language model, a few GB)."
Write-Host "Everything stays on this PC. To use the OpenAI API instead, change it in Preferences."
Write-Host "Find it in the Start menu and on the desktop. Uninstall from Settings > Apps > DroidNote."

if ($env:DROIDNOTE_NO_LAUNCH -ne "1") {
    Step "Opening DroidNote"
    # Inside a package the app itself would also keep its data in the private copy.
    if ($Family) { Start-Process -FilePath "explorer.exe" -ArgumentList "`"$AppExe`"" }
    else { Start-Process -FilePath $AppExe | Out-Null }
}
