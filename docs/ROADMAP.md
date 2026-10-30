# Roadmap

Where DroidNote is going, in rough order. Dates are not promises; items move when users show us something more useful. Shipped items go to the [changelog](../CHANGELOG.md); the detailed engineering notes behind the recent work are in [melhorias.md](melhorias.md) (Portuguese).

## Principles that do not move

- **Local first.** Everything works with nothing leaving the PC. Cloud is an opt-in per engine, with the user's own key.
- **No bot in the call.** DroidNote listens to the machine's audio; nobody has to admit a participant.
- **No account, no telemetry.** Install, pick a model, start.
- **Plain language.** Screens for lay users explain models and hardware in one sentence, not a paragraph.

## Now (2.3)

- [x] Mind map built from the minutes, editable, exportable as PNG and outline
- [x] Memory across meetings in a series (what was decided and what stayed open)
- [x] Session context documents (agenda, slides, contracts) feeding minutes and chat
- [x] Hardware-aware default model (RAM and graphics memory) and Gemma 4 / Qwen 3.6 catalog
- [x] Branded PDF and Word exports
- [x] Changelog-driven release notes and the community files of this repository
- [x] Unattended install script and one-line install commands for AI agents
- [ ] Authenticode signing of the installer

## Next

- **Speaker names from the calendar.** When an invitation is connected, propose participant names for unknown voices instead of "Speaker 2".
- **Per-template minutes.** Different minute shapes for a lecture, a customer call and a stand-up, chosen once per series.
- **Task sync.** Send action items to Microsoft To Do or a plain `.ics` with due dates; keep "done" in sync both ways.
- **Faster first minutes.** Stream the minutes while the model writes, instead of waiting for the full document.
- **Smaller local footprint.** Quantised Whisper variants selected by the wizard; remove the dependency on a 1.5 GB ASR model for the smallest tier.

## Later

- **macOS.** The React app and the backend already run there; what is missing is the system-audio capture layer (ScreenCaptureKit) and the installer.
- **Linux.** PipeWire capture; AppImage.
- **Local embeddings for search.** Semantic search across all meetings without the OpenAI key.
- **Shared read-only exports.** A single HTML file with transcript, minutes and mind map for people who do not have DroidNote.
- **Plugins for other LLM servers.** LM Studio and llama.cpp servers that speak the OpenAI API, selectable like Ollama.

## Not planned

- A hosted DroidNote with accounts and cloud storage.
- Joining calls as a participant or bot.
- Selling or training on user data, in any form.

## Suggesting something

Open a [feature request](https://github.com/droidwerk/droidNote/issues/new?template=feature_request.yml) describing the situation first and the solution second. Items here start as issues with enough thumbs-up or a clear use case. Code is written by DroidWerk and invited collaborators; see [CONTRIBUTING.md](../.github/CONTRIBUTING.md).
