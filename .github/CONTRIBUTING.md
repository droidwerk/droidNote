# Contributing to DroidNote

DroidNote is open source under the AGPL-3.0: you can use it, study it, change it and share it. Code in **this** repository, though, is written by DroidWerk and by collaborators we invite. We do not accept unsolicited pull requests; they are closed automatically with a note pointing here.

This page says what we do welcome, and how invited collaborators work.

| | |
| --- | --- |
| 🐛 Bugs | [Issues → Bug report](https://github.com/droidwerk/droidNote/issues/new?template=bug_report.yml) |
| 💡 Ideas | [Issues → Feature request](https://github.com/droidwerk/droidNote/issues/new?template=feature_request.yml) |
| 🙋 Help | [SUPPORT.md](SUPPORT.md) |
| 🔒 Security | [SECURITY.md](SECURITY.md) — never a public issue |
| 🗺️ Direction | [docs/ROADMAP.md](../docs/ROADMAP.md) |

## Everyone is welcome to

- Report bugs with a clear reproduction. These are the most valuable thing you can send.
- Propose features by describing the situation you are in, not only the solution.
- Point out a wrong translation or a confusing text, with the screen it appears on.
- Fork the project and change it for your own needs, as the licence allows. If you distribute your version, give it its own name ([TRADEMARK.md](../TRADEMARK.md)).

If you have already written a fix, describe it in an issue (what, where, how you tested). When it fits, we either apply it ourselves with credit to you, or invite you as a collaborator so you can open the pull request.

## Why by invitation

Keeping the code written by a known group keeps authorship clear, keeps the writing style of the app consistent, and lets DroidWerk answer for every line that ships to users. It is the same model other small open-source products use.

## Being invited

We invite people who have reported good issues, who understand the product promise (**local-first, no bot in the call, no account required**) and who have time for review rounds. Invitations come from the maintainers; there is no form to request one.

## For invited collaborators

### Setup

The [development guide](../docs/development.md) has the full walkthrough. In short:

- Windows 10/11 x64, Python 3.11+, Node 20+ (CI uses 22), Rust (for the Tauri shell).
- `dev.ps1` starts the backend and the Vite dev server together.
- Backend tests: `cd backend && python -m pytest -q`.
- Frontend type-check: `cd desktop && npx tsc --noEmit`.

### Pull requests

1. Branch from `main`; never push to `main` directly. Every push to `main` ships a release.
2. One change per pull request.
3. Add or update tests for behaviour you change. UI changes are verified on the screen; say how in the description.
4. Add a line under **Unreleased** in [CHANGELOG.md](../CHANGELOG.md) when users can notice the change.
5. Texts the user sees exist in seven languages (`desktop/src/shared/i18n/catalogs`). Add every new key to all seven.
6. Keep the writing style of the app: short sentences, no filler, no jargon on screens meant for lay users.
7. Fill the pull request template. A maintainer reviews every pull request; review comments are about the code, never about the person.

Commit messages: `type(scope): summary`, imperative mood. Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `release`. `[release minor]` or `[release major]` in a merge commit bumps the version accordingly; `[skip release]` ships nothing.

### What will not be merged

- Anything that uploads audio or text without the user choosing it explicitly.
- Telemetry or analytics of any kind.
- Models or dependencies whose licence does not allow the use DroidNote makes of them.
- Features that rename or imitate another product's distinctive feature names.

### Licensing of contributions

Everything merged here is licensed under the AGPL-3.0 like the rest of the project ([LICENSE](../LICENSE)); you keep the copyright of what you write. By opening a pull request you certify the [Developer Certificate of Origin](https://developercertificate.org/): the work is yours or you have the right to submit it under this licence. Add `Signed-off-by: Your Name <email>` to your commits (`git commit -s`) to say so.

## Code of conduct

Everyone participating here follows the [code of conduct](CODE_OF_CONDUCT.md).
