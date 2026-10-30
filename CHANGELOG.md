# Changelog

All notable changes to DroidNote are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

`desktop/src-tauri/tauri.conf.json` is the version source of truth; the release
workflow bumps every copy of the number together and moves the **Unreleased**
section below into a dated release. Write entries here as you go; the release
notes on GitHub are built from them.

## [Unreleased]

## [2.2.8] — 2026-10-30

### Changed
- OpenAI transcription now uses `gpt-transcribe`, the current speech-to-text model (US$ 0.0045/min), with the language sent as a `languages[]` hint and the detected language read back from the response. The deprecated `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-mini-transcribe-2025-12-15`, `gpt-4o-transcribe-diarize` and `whisper-1` (OpenAI shuts them down on 2027-02-26) are gone from the list; a saved preference that still names one of them switches to `gpt-transcribe` on the next start, with nothing to do. Who said what keeps coming from the local voice engine, as before. The realtime models (`gpt-live-transcribe`, `gpt-realtime-whisper`) only exist in OpenAI's realtime sessions, which the app does not use.
- OpenAI minutes, chat and mind map now use `gpt-6-luna` by default (US$ 0.10 / 0.50 per million tokens, cheaper than the old `gpt-4o-mini`), with `gpt-5.6-luna` and `gpt-5.6-terra` as the other choices. `gpt-4o-mini`, `gpt-4.1-mini` and `gpt-4o` (OpenAI shuts them down on 2027-01-14) are gone from the list; a saved `gpt-4o-mini` or `gpt-4.1-mini` becomes `gpt-6-luna` and a saved `gpt-4o` becomes `gpt-5.6-terra` on the next start. Requests ask for no reasoning (`reasoning_effort: none`) so the minutes come back as fast and as cheap as before, and a generation parameter the model rejects is dropped and the request retried instead of failing the minutes.

### Fixed
- `install.ps1` run from a terminal inside a packaged app (the Claude desktop app is one) now installs through a small `install.cmd` opened by Explorer instead of a scheduled task, so DroidNote lands in your real profile with its Start menu and *Settings › Apps* entries.

## [2.2.7] — 2026-10-30

_No notes were written for this release._

## [2.2.6] — 2026-10-30

### Added
- Install without clicks: `install.ps1` downloads the latest release, verifies its SHA-256 and installs silently; the first start skips the wizard and prepares the recommended local models. One-line commands for Claude Code, Codex, Gemini, Copilot and Cursor in the README, with a machine-readable list for the website.
- Repository: AGPL-3.0 license with trademark and third-party notices, English and Portuguese READMEs with screenshots, this changelog (now the source of the release notes), contributing, support and security guides, issue and pull request templates, roadmap and release docs.
- Mind map tab built from the minutes (topics, decisions, actions, open items, material, "since last time"), with every leaf linked to the speech, editing saved per meeting, "Rebuild from minutes" and "Reorganize with AI". Export as PNG or Markdown outline.
- Memory across meetings: meetings with the same title or people form a series; the Memory tab shows what was decided and what stayed open before a meeting, and what was resolved, changed or is new after it. Resolved items can close their tasks in one click.
- Context tab: attach agenda, slides or contracts to a meeting; the minutes and the chat use them.
- Notes get their own side tab; the Document tab shows only the AI minutes.
- OpenAI key walkthrough in Preferences and in the setup wizard; plain-language description for every model, local or cloud.
- Setup wizard shows a "Your computer" analysis (RAM, graphics card, free disk) and explains the recommended models.
- Markdown rendering in chat answers and in the mini console.
- Session documents are searchable by the chat when the meeting is in focus.

### Changed
- Local model catalog: Gemma 4 (E2B/E4B/12B/26B) and Qwen 3.6 35B-A3B replace the previous defaults; the default is chosen by RAM and, when there is a graphics card, by what fits in its memory.
- OpenAI transcription list: `gpt-4o-mini-transcribe` is the default; `gpt-4o-mini-transcribe-2025-12-15` and `gpt-4o-transcribe-diarize` added. The diarize model's speaker cuts feed the voice engine so quick exchanges inside one window are split.
- PDF and Word exports redesigned with the DroidNote look: orange title, metadata line, ruled sections, bullets, mono timestamps, footer.
- Preferences › Engine with far less text; consent and mini-console buttons moved to the live page header.
- Library, chat rail and page headers adapt to windows between 760 and 1180 px.

### Fixed
- PDF export failed with "Failed to fetch" (missing import on the server).
- Ollama requests opened the model's full context window (131k tokens on Gemma 4), which filled the graphics card and slowed generation to ~3 tokens/s; the context is now sized to the request (69 tokens/s on the same card).
- Slow-but-progressing local models no longer die at a 3-minute timeout; only a model that stops responding does.
- Calendar (ICS) fetch crashed on redirects because the private-address guard was synchronous.
- Minutes whose overview came back as a list of sentences showed Python brackets.
- File names suggested for exports contained `/` and `:` from the meeting title, which Windows rejects.
- Translations for model ids with dots (`gpt-4.1-mini`, `qwen2.5:3b`) never resolved.
- Attachments stayed locked to a chat whose first question failed.
- Repeated lines in minutes (topics, highlights, decisions) and duplicated tasks between manual and AI-created ones.

### Removed
- Flowchart ("relations" and "flow" diagrams) — replaced by the mind map.

## [2.2.5] — 2026-10-29

### Added
- Live "speaking now" badge recognises known people by voiceprint before the transcript arrives.
- `Ctrl+K` search covers notes, minutes and tasks, not only the transcript.

### Changed
- Voice engine tuned on real recordings: fewer phantom voices, far less relabelling during a meeting, faster regrouping in the first minute.

## [2.2.4] — 2026-10-28

### Added
- Documents attached to the chat (PDF, Word, Excel, CSV, text) with per-page citations.
- Floating menus (language, sources) open downward and scroll instead of clipping.

### Removed
- Folder sidebar and session tag chips in favour of the library folders.

## [2.2.3] — 2026-10-28

### Added
- Notes typed during the recording, pinned to the moment of speech, with kinds (decision, task, important, question) that guide the minutes.
- Task center: actions from the minutes become tasks with owner and due date; manual tasks; done state kept across regenerated minutes.
- Calendar brief: upcoming meetings from an ICS address with what stayed pending from similar meetings.

## [2.2.2] — 2026-10-19

### Changed
- Maintenance release: dependency and build updates.

## [2.2.1] — 2026-09-10

### Fixed
- Hardened `.gitignore` so audio, transcripts and API keys can never enter the repository; build paths cleaned.

## [2.2.0] — 2026-09-10

### Fixed
- Chat answers in the interface language, regardless of the transcript or question language.
- Model downloads trust the Windows certificate store (proxies and HTTPS-inspecting antivirus).

### Added
- Architecture and development guides; repository README.

## [2.1.0] — 2026-09-10

### Added
- In-app update notice when a new release is published.

## [2.0.1] — 2026-09-10

### Fixed
- Stability fixes after the 2.0.0 launch.

## [2.0.0] — 2026-09-10

### Added
- Chat over the captured sessions, with sources.

## [1.0.1] — 2026-09-09

### Fixed
- First-run fixes after 1.0.0.

## [1.0.0] — 2026-09-09

### Changed
- ASR setup and error handling reworked for the first public release.

## [0.1.0] — 2026-09-08

### Added
- First version of the DroidNote Windows app: capture, local transcription, minutes.

[Unreleased]: https://github.com/droidwerk/droidNote/compare/v2.2.8...HEAD
[2.2.8]: https://github.com/droidwerk/droidNote/compare/v2.2.7...v2.2.8
[2.2.7]: https://github.com/droidwerk/droidNote/compare/v2.2.6...v2.2.7
[2.2.6]: https://github.com/droidwerk/droidNote/compare/v2.2.5...v2.2.6
[2.2.5]: https://github.com/droidwerk/droidNote/compare/v2.2.4...v2.2.5
[2.2.4]: https://github.com/droidwerk/droidNote/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/droidwerk/droidNote/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/droidwerk/droidNote/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/droidwerk/droidNote/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/droidwerk/droidNote/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/droidwerk/droidNote/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/droidwerk/droidNote/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/droidwerk/droidNote/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/droidwerk/droidNote/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/droidwerk/droidNote/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/droidwerk/droidNote/releases/tag/v0.1.0
