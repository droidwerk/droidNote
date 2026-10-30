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
    no Settings > Apps entry. So in that case steps 1-5 run through a one-time scheduled task of
    the current user, outside the package, and this window shows their output.

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

function Install-OutsidePackage([string] $Family) {
    Step "This terminal runs inside the app package $Family"
    Step "Installing through a one-time scheduled task, so DroidNote gets its Start menu entry and appears in Settings > Apps"

    # The task's output goes to a file in the real %TEMP%: this side reads through to it,
    # while anything written from here could land in the package's private copy.
    $id = [guid]::NewGuid().ToString("N")
    $log = Join-Path $env:TEMP "droidnote-install-$id.log"
    $vars = ""
    foreach ($name in "DROIDNOTE_AGENT", "DROIDNOTE_LANGUAGE", "DROIDNOTE_NO_LAUNCH") {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) { $vars += "`$env:$name = '" + $value.Replace("'", "''") + "'; " }
    }
    $quotedLog = "'" + $log.Replace("'", "''") + "'"
    $command = "try { & { $vars irm '$Base/install.ps1' | iex } *> $quotedLog; exit 0 } catch { `$_ | Out-File -Append $quotedLog; exit 1 }"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))

    $task = "DroidNote install $id"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $encoded"
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    try {
        Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings | Out-Null
    } catch {
        Fail "could not create the scheduled task ($($_.Exception.Message)). Run the same command in a PowerShell window opened from the Start menu."
    }

    $result = $null
    $shown = 0
    try {
        Start-ScheduledTask -TaskName $task
        $deadline = (Get-Date).AddHours(1)
        do {
            Start-Sleep -Seconds 2
            # 267011: has not run yet. 267009: running.
            $result = (Get-ScheduledTaskInfo -TaskName $task).LastTaskResult
            $lines = @(Get-Content $log -ErrorAction SilentlyContinue)
            # The last line may still be half written.
            for (; $shown -lt $lines.Count - 1; $shown++) { Write-Host $lines[$shown] }
        } while (($result -eq 267011 -or $result -eq 267009) -and (Get-Date) -lt $deadline)
        $lines = @(Get-Content $log -ErrorAction SilentlyContinue)
        for (; $shown -lt $lines.Count; $shown++) { Write-Host $lines[$shown] }
    } finally {
        Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item -Force $log -ErrorAction SilentlyContinue
    }
    if ($result -ne 0) { Fail "the install outside the app package ended with code $result (see the lines above)." }

    # A previous install from inside this package only exists in its private copy. The
    # program files can go; the data folder (%APPDATA%) is left alone.
    $ghost = Join-Path $env:LOCALAPPDATA "Packages\$Family\LocalCache\Local\DroidNote"
    if (Test-Path $ghost) {
        Remove-Item -Recurse -Force $ghost -ErrorAction SilentlyContinue
        Step "Removed the earlier copy that was installed inside $Family"
    }
}

Write-Host ""
Write-Host "DroidNote installer" -ForegroundColor Cyan
Write-Host "Local meeting transcription, minutes and memory, on this PC." -ForegroundColor DarkGray
Write-Host ""

if ($env:OS -ne "Windows_NT") { Fail "DroidNote runs on Windows 10/11." }
if (-not [Environment]::Is64BitOperatingSystem) { Fail "DroidNote needs 64-bit Windows." }

$Family = Get-PackageFamily
if ($Family) {
    Install-OutsidePackage $Family
} else {
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
    Write-Host "Find it in the Start menu and on the desktop. Uninstall from Settings > Apps > DroidNote."

    if ($env:DROIDNOTE_NO_LAUNCH -ne "1") {
        Step "Opening DroidNote"
        Start-Process -FilePath $AppExe | Out-Null
    }
}
