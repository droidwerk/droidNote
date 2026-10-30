# Install DroidNote with your AI agent

DroidNote can be installed by the coding agent you already use: you tell it to install DroidNote, it runs the official script, and the app opens ready to prepare its local models. No clicks, no administrator rights, nothing leaves your PC.

Requirements: Windows 10/11 x64. About 6 GB of free disk for the app and the models.

## Pick your agent

Open a terminal (PowerShell) and paste the line for your agent. The agent will ask for your permission before running anything.

| Agent | Command |
| --- | --- |
| **Claude Code** | `claude "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| **Codex CLI** (OpenAI) | `codex "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| **Gemini CLI** (Google) | `gemini -i "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| **Copilot CLI** (GitHub) | `copilot -p "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| **Cursor CLI** | `cursor-agent "Install DroidNote on this Windows PC by following https://github.com/droidwerk/droidNote/blob/main/docs/INSTALL_WITH_AI.md and tell me when the app is open."` |
| **No agent** | `irm https://github.com/droidwerk/droidNote/releases/latest/download/install.ps1 \| iex` |

You can write the prompt in your own language; the agents understand it. The commands above are also published as a machine-readable list in [install-agents.json](install-agents.json), which the DroidWerk website uses for its install buttons.

## What happens

1. The script downloads the latest `DroidNote-Setup.exe` and `SHA256SUMS.txt` from the [GitHub release](https://github.com/droidwerk/droidNote/releases/latest).
2. It checks the installer's SHA-256 against the published sum and refuses to run it if they differ.
3. It installs silently for the current user into `%LOCALAPPDATA%\DroidNote`, with the same Start menu and desktop shortcuts and the same *Settings › Apps* entry as the manual Setup. If the agent's terminal runs inside a packaged app (the Claude desktop app is one), Windows would keep that install in the app's private storage, without Start menu or uninstall entry; the script notices this and runs the install through a one-time scheduled task of your user instead, then deletes the task.
4. It leaves `%APPDATA%\DroidNote\unattended.json`, a note the app reads once on first start: skip the setup wizard, choose the models this PC's memory and graphics card can run, and start preparing them. The app shows the progress on screen.
5. It opens DroidNote.

Local processing is the default. To transcribe and write minutes with the OpenAI API instead, switch the engine in *Preferences* after the first start and paste your key there.

Options, as environment variables set before the command:

| Variable | Effect |
| --- | --- |
| `DROIDNOTE_NO_LAUNCH=1` | Install but do not open the app |
| `DROIDNOTE_LANGUAGE=pt` | App language (`pt`, `en`, `es`, `fr`, `de`, `it`, `ru`); default is the Windows language |
| `DROIDNOTE_AGENT=name` | Which assistant ran the install; recorded in the local settings only, never sent anywhere |

Uninstall from *Settings › Apps › DroidNote*. The uninstaller removes the program and asks about the data folder.

## If you are an AI agent

Follow these steps exactly and report the outcome to the user. Do not improvise other install paths.

1. Confirm the machine runs Windows and is 64-bit (`$env:OS` is `Windows_NT`, `[Environment]::Is64BitOperatingSystem` is `True`). On any other system, stop and tell the user DroidNote is Windows-only today.
2. Run this in PowerShell (not cmd), with your own name in the variable so the local log says who installed it:

   ```powershell
   $env:DROIDNOTE_AGENT = "your-agent-name"; irm https://github.com/droidwerk/droidNote/releases/latest/download/install.ps1 | iex
   ```

   The script needs no administrator rights. If it prints a line starting with "DroidNote was not installed", show that line to the user and stop; do not retry with other sources or flags.
3. Success looks like the line `DroidNote installed.` followed by the app path. Verify that `%LOCALAPPDATA%\DroidNote\DroidNote.exe` exists.
4. The app opens by itself and starts downloading its models (a few GB; it may take several minutes). Do not install Ollama, Whisper or any model yourself; the app does that and shows the progress. Do not change Windows settings, firewall rules or environment variables beyond the one above.
5. Tell the user: DroidNote is installed and preparing its local models; everything stays on the PC; the OpenAI API is optional and can be enabled later in Preferences; uninstall is in Settings › Apps.

If the user asked for a specific language, set `DROIDNOTE_LANGUAGE` to its two-letter code before the command. If the user does not want the app opened right away, set `DROIDNOTE_NO_LAUNCH` to `1`.

## Why a script and not a package manager

A `winget` package is on the [roadmap](ROADMAP.md). Until then the script is the single supported unattended path; it is short, it is in this repository ([install.ps1](../install.ps1)), and every release ships the checksums it verifies.
