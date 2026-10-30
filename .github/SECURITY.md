# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| Latest release on the `main` line | ✅ Fixes, including security fixes |
| Older releases | ❌ No backports — update from the in-app notice or [the releases page](https://github.com/droidwerk/droidNote/releases/latest) |

## What DroidNote does with your data

- Audio, transcripts, minutes, tasks and keys are stored under `%APPDATA%\DroidNote` on your PC. Nothing is sent anywhere in local mode.
- With the OpenAI API enabled, audio windows and minutes text are sent to OpenAI under your own key. The key is stored encrypted with Windows DPAPI for the current user.
- Local models come only from their official sources (Hugging Face for Whisper and the voice embedder, the Ollama registry for language models) and the installer for Ollama is checked against a pinned SHA-256.
- The desktop app talks to its backend over `127.0.0.1` with a per-session token. The backend never listens on other interfaces.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Use one of these:

1. [GitHub private vulnerability reporting](https://github.com/droidwerk/droidNote/security/advisories/new) (preferred).
2. Email **contato@droidwerk.com.br**.

Include what you found, how to reproduce it, the version (Preferences › About) and what you think the impact is. A proof of concept helps; please do not test against other people's machines.

## What to expect

| Step | Target |
| --- | --- |
| Acknowledgement | 48 hours |
| First assessment | 5 business days |
| Fix for a confirmed issue | Next release; critical issues get a dedicated patch release |

We credit reporters in the changelog unless they prefer not to be named.
