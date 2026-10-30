# Support

## Where to get help

| Channel | Best for |
| --- | --- |
| [GitHub Issues](https://github.com/droidwerk/droidNote/issues) | Bugs, feature requests and questions — use the templates |
| Security problems | **Never a public issue** — see [SECURITY.md](SECURITY.md) |
| Commercial questions | [droidwerk.com.br](https://www.droidwerk.com.br/) |

## Before filing a bug

1. Update to the latest release; fixes ship with every push to `main`.
2. Check **Preferences › Transcription**: is the engine you expect selected, and does the status line say the local engine is up (or the key is saved)?
3. Search the open issues and add your details to an existing one instead of opening a duplicate.
4. For local models, note your RAM, graphics card and the model names shown in Preferences — the bug template asks for them.

## Common questions

**The minutes or the mind map take minutes to appear.**
With local models the speed depends on the model fitting in your graphics card's memory. Preferences shows which model is selected; the setup wizard's "Your computer" box explains what fits. On a card with 8 GB, `gemma4:e4b` answers in seconds and `gemma4:12b` does not.

**Windows warns that the installer is unrecognised.**
The installer carries no Authenticode signature yet. Use *More info → Run anyway* if you downloaded it from this repository.

**Where are my files, and how do I remove everything?**
Data in `%APPDATA%\DroidNote`, the program in `%LOCALAPPDATA%\DroidNote`. The uninstaller removes the program and offers to remove the data folder. Ollama models live in Ollama's own folder (`~/.ollama/models`) and are removed with `ollama rm <model>`.

**Does DroidNote tell the other people in the call that it is recording?**
No. Recording other people needs their consent; the live screen has a one-click notice you can paste into the meeting chat.

## Response expectations

DroidNote is maintained by a small team. Issues are triaged within a week; there is no guaranteed response time for questions. Clear reproductions and screenshots are answered first.
