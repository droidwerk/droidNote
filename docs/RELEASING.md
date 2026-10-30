# Releasing

DroidNote ships continuously: **every push to `main` becomes a release** that users receive through the in-app update notice. This page says how the numbers work and what happens between the push and the download.

## Version numbers

[Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`, tagged `vX.Y.Z`.

| Part | When | How to trigger |
| --- | --- | --- |
| **patch** | Fixes, small adjustments, text, dependency updates | Default for any push |
| **minor** | A new feature or a visible change in behaviour | `[release minor]` in the merge commit message, or *Run workflow → minor* |
| **major** | Data format or settings that older versions cannot read, dropped platforms | `[release major]` in the merge commit message, or *Run workflow → major* |

A push that only touches Markdown files, `docs/`, `LICENSE` or the issue templates does not release (the workflow's `paths-ignore`), and `[skip release]` in the commit message skips it for anything else. The automated version commit carries `[skip ci]` so it does not trigger itself.

The version lives in eight files that must agree (`tauri.conf.json` is the source of truth); `installer/bump_version.py` updates all of them and fails if any copy is missing.

## What the workflow does

[`.github/workflows/release.yml`](../.github/workflows/release.yml), two jobs:

1. **build** (Windows runner, read-only): checks out the current `main`, runs the backend tests, computes the next version, builds the NSIS installer and the bootstrap `DroidNote-Setup.exe`, uploads both as an artifact.
2. **release** (Linux runner, the only job with write permission): re-applies the same version bump on the same commit, rolls the changelog, commits `release: DroidNote X.Y.Z [skip ci]`, tags `vX.Y.Z`, pushes, and publishes the GitHub release with the two installers and the notes from the changelog.

Runs are serialised (`concurrency: release-main`), so two quick pushes produce two releases in order, each on top of the previous version commit.

## Changelog

[`CHANGELOG.md`](../CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Write entries under **Unreleased** as part of the change itself, in the user's words (what they can see or do now), grouped as *Added / Changed / Fixed / Removed / Security*.

At release time `scripts/release_changelog.py` renames **Unreleased** to the new version with the date, opens an empty Unreleased section, fixes the compare links and hands the section to `gh release create --notes-file`. The workflow warns when Unreleased is empty and publishes the release with a placeholder note. Preview what the next release will say with:

```bash
python scripts/release_changelog.py --check
```

## Checklist for a release-worthy merge

- [ ] `cd backend && python -m pytest -q` and `cd desktop && npx tsc --noEmit` pass locally.
- [ ] `CHANGELOG.md` has the entries under Unreleased.
- [ ] Texts exist in all seven language catalogs.
- [ ] If settings or the database schema changed: the migration runs on an existing `%APPDATA%\DroidNote\droidnote.db` and the old app can still be uninstalled cleanly.
- [ ] If the local model catalog changed: the model ids exist on the Ollama registry and `OLLAMA_DOWNLOAD_GB` has their sizes.
- [ ] Decide the bump: patch by default, `[release minor]` for features.

## Pre-releases

For a build that testers should try before everyone gets it, run the workflow manually and publish the release as a pre-release (`gh release edit vX.Y.Z --prerelease`). The in-app update check ignores pre-releases, so only people who download from the releases page receive them. Promote it by clearing the flag; no rebuild is needed.

## Hotfix

A hotfix is an ordinary push to `main` with a `fix:` commit. There are no release branches; the previous release is always the parent of the next one.

## Signing

Installers are not Authenticode-signed yet; Windows shows the SmartScreen warning on first run. Signing is on the [roadmap](ROADMAP.md) and will not change this flow beyond one extra step in the build job.
