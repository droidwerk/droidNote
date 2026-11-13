# Changelog

All notable changes to DroidNote are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

`desktop/src-tauri/tauri.conf.json` is the version source of truth; the release
workflow bumps every copy of the number together and moves the **Unreleased**
section below into a dated release. Write entries here as you go; the release
notes on GitHub are built from them.

## [Unreleased]

## [2.3.1] — 2026-11-13

### Added
- Chat context with several conversations: pick them with "Choose conversations" (search, last 7 or 30 days, folder); the answer uses only those, a line above the box says how many, and the pick is saved on the chat and restored when you reopen it.
- Chat: Stop button (the partial answer is kept and marked as interrupted), rename a chat, "Try again" after an error without repeating the question, "Generate again" on the last answer, history grouped by Today, Yesterday, 7 days and Earlier.
- Full guided tour in 9 chapters (41 steps): chapter picker, skip a chapter, resume where you stopped, and a "?" on each page to replay its chapter. It never clicks, records or changes settings for you.
- Help tab: a plain-language manual, keyboard shortcuts and frequently asked questions.
- Welcome dialog shown once on a fresh install, in the install language, and a release-notes dialog shown once per version to users who updated.
- Key safety seal in Preferences: the OpenAI key stays on this PC, encrypted by Windows, and only goes to OpenAI.

### Changed
- Chat leaves beta. When conversations are selected, search, citations and the conversation list are limited to them; with none selected the chat uses all conversations.
- Series memory follows the folder: a meeting in a folder links only meetings of the same folder, and each linked meeting shows why (same folder, similar title, same people).
- The conversation tab "Document" is now "Ata"; the chat uses "New chat" and "Choose conversations".
- Time stamps in answers link to the right meeting when several are in context.
- Tasks show relative due dates anchored to the meeting date ("Tomorrow · 13/11") and filter by one person per button.
- The mind map opens with the main branches, fitted and using the full width.
- The engine switch in Preferences applies at once, like the one in the sidebar. OpenAI prices were replaced by a link to OpenAI's pricing page.
- Readability: higher-contrast text and buttons, a visible keyboard focus ring, tabs that move with the arrow keys.
- The recording notice mentions OpenAI and a transfer outside Brazil when the cloud engine is on.

### Fixed
- The chat answered with excerpts from every conversation even when one was selected.
- The "Who spoke when" timeline now marks a long final silence instead of looking empty.

## [2.3.0] — 2026-11-03

### Added
- Chat answers render Markdown properly: tables, headings, lists, links, and math with LaTeX (`$...$` inline, `$$...$$` blocks) through KaTeX, all offline.
- Chat citations: every excerpt the assistant used is numbered, a `[n]` in the answer is a chip that opens the recording at that exact moment, and the sources footer lists one entry per recording or document instead of one per excerpt.
- Chat modes behind a gear button: Normal, Quick (short answer, half the context, faster on a local model), Study (from the intuition up, with recap and practice questions) and Solve (a technical problem gathered from meetings, documents and links, ending in a ready-to-paste prompt for Claude Code, Codex, Cursor or any coding agent, with a "Copy prompt" action). A "sources only" switch keeps the model from using general knowledge, and a scope picker limits the question to the focused recording, the last 7 or 30 days, or the recordings with a given person or tag.
- Slash commands in the question box (`/summary`, `/tasks`, `/decisions`, `/glossary`, `/flashcards`, `/exercises`, `/one-page`, `/exam`); the four study ones also appear as chips when a recording is focused.
- Save an answer: as a note of the recording, as tasks (one per list item), or as PDF, Word or Markdown with the DroidNote look.
- Charts: when numbers from the sources call for it, the assistant emits a `chart` block and the chat draws a bar or line chart (with a values table), no external library.
- Images in the chat: a photo of the board or a slide screenshot goes with the question (picked, dropped or pasted), downscaled on the device, read by a vision-capable model (Gemma 4 locally, or OpenAI) and kept with the message. A model without vision gets a clear message.
- Links as sources: attach a web page (its text) or a YouTube video (its captions, or a local Whisper transcription of the audio when there are none, via yt-dlp). A URL pasted alone into the empty question box is attached directly.
- Export a recording as the note only or the transcript only, in Markdown, PDF or Word, besides the full JSON.

### Changed
- Backend packages are installed from `backend/uv.lock` with uv (`uv sync --frozen`) in the installer build, the release workflow and `dev.ps1`, so every build ships the same versions. Pillow, urllib3, certifi and filelock minimums raised past their open CVEs.
- The web reader identifies itself as DroidNote with its version and project address instead of imitating a browser (Wikipedia and others refuse the latter).

### Fixed
- The "In the room" list starts empty on every new recording and a finished recording no longer lends its participants to the next one; a chosen "You on the microphone" is never replaced by a single participant, so the microphone stops being attributed to the other person in a two-person call.
- PDF export failed with "Failed to fetch": the packaged backend excluded Pillow, which reportlab imports. Pillow and reportlab are now bundled, and a server error reaches the app as a readable message with CORS headers instead of a network failure.
- Markdown styles in the chat never loaded because a stray script had been pasted into `assist.css`.
- Security: the link reader refuses loopback, link-local and credentialed URLs; the export "Save" dialog and the file write now run in Rust, so the interface never supplies a disk path and the webview lost its dialog permission; chat links open in the system browser; the content policy allows the chat's image thumbnails.

## [2.2.10] — 2026-10-30

### Added
- Preferences › Capture: "I use headphones". With headphones the meeting audio never reaches the microphone, so the echo filter is switched off and nothing you say is cut. Without it, the filter that keeps the speaker from being transcribed as you could also drop your own voice while the other side was talking.

### Fixed
- Voice recognition no longer labels two different voices as the same person, nor two people as one voice. A saved voiceprint used to link a whole voice to a person on the strength of a single matching window, and the link was then written back as if you had named the voice; now a person can be one voice per meeting, the link needs the whole voice to match the voiceprint, automatic matches are recomputed on every pass instead of being stored, and only the names you give are kept. Two voices are also no longer merged when their voiceprints are as close as 0.45 (real calls had two people at 0.51); the threshold is 0.55. Voiceprints learn only from clear, confident speech (at least 1 s and 0.5 confidence), so a wrong label no longer pollutes a person's voiceprint for the next meeting.

## [2.2.9] — 2026-10-30

_No notes were written for this release._

## [2.2.8] — 2026-10-30

### Changed
- OpenAI transcription now uses `gpt-transcribe`, the current speech-to-text model (US$ 0.0045/min), with the language sent as a `languages[]` hint and the detected language read back from the response. The deprecated `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-mini-transcribe-2025-12-15`, `gpt-4o-transcribe-diarize` and `whisper-1` (OpenAI shuts them down on 2027-02-26) are gone from the list; a saved preference that still names one of them switches to `gpt-transcribe` on the next start, with nothing to do. Who said what keeps coming from the local voice engine, as before. The realtime models (`gpt-live-transcribe`, `gpt-realtime-whisper`) only exist in OpenAI's realtime sessions, which the app does not use.
- OpenAI minutes, chat and mind map now use `gpt-6-luna` by default (US$ 0.10 / 0.50 per million tokens, cheaper than the old `gpt-4o-mini`), with `gpt-5.6-luna` and `gpt-5.6-terra` as the other choices. `gpt-4o-mini`, `gpt-4.1-mini` and `gpt-4o` (OpenAI shuts them down on 2027-01-14) are gone from the list; a saved `gpt-4o-mini` or `gpt-4.1-mini` becomes `gpt-6-luna` and a saved `gpt-4o` becomes `gpt-5.6-terra` on the next start. Requests ask for no reasoning (`reasoning_effort: none`) so the minutes come back as fast and as cheap as before, and a generation parameter the model rejects is dropped and the request retried instead of failing the minutes.

### Fixed
- Voices no longer vanish, swap names or merge mid-meeting. The periodic regrouping estimated a different number of voices on every pass (3, 5, 3, 5…) and rewrote every label each time; now a new count only takes effect once it repeats on two consecutive passes, two voices that belong to different people are never merged (a group that mixes them is split again), and a named voice absorbed by an unnamed one keeps its name.
- Someone who joins a call speaking in short sentences gets their own voice. Short pieces that match nobody now add up until they found a voice (2.5 s), instead of being glued to the most similar existing voice for the rest of the meeting.
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

[Unreleased]: https://github.com/droidwerk/droidNote/compare/v2.3.1...HEAD
[2.3.1]: https://github.com/droidwerk/droidNote/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/droidwerk/droidNote/compare/v2.2.10...v2.3.0
[2.2.10]: https://github.com/droidwerk/droidNote/compare/v2.2.9...v2.2.10
[2.2.9]: https://github.com/droidwerk/droidNote/compare/v2.2.8...v2.2.9
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
