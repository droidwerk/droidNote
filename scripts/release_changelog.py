"""Turn the Unreleased section of CHANGELOG.md into a dated release.

Usage: python scripts/release_changelog.py X.Y.Z [--date YYYY-MM-DD] [--notes PATH] [--check]

- Renames ``## [Unreleased]`` to ``## [X.Y.Z] — date`` and opens a fresh, empty
  Unreleased section above it.
- Updates the compare links at the bottom of the file.
- Writes the release's section body to ``--notes`` (for ``gh release create
  --notes-file``) and prints it.
- ``--check`` only prints the notes and changes nothing; it exits 1 when the
  Unreleased section is empty (the workflow turns that into a warning).

The release workflow calls this after bumping the version; it is also handy
locally to preview the notes of the next release.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/droidwerk/droidNote"
HEADING = re.compile(r"^## \[(?P<name>[^\]]+)\](?: — (?P<date>\d{4}-\d{2}-\d{2}))?\s*$", re.M)
LINK = re.compile(r"^\[(?P<name>[^\]]+)\]: \S+\s*$", re.M)


def split_sections(text: str) -> tuple[str, list[tuple[str, str | None, str]], str]:
    """Return (preamble, [(name, date, body)], links footer)."""
    matches = list(HEADING.finditer(text))
    if not matches:
        raise SystemExit("CHANGELOG.md has no '## [version]' headings")
    preamble = text[: matches[0].start()]
    footer_start = len(text)
    first_link = LINK.search(text, matches[-1].end())
    if first_link:
        footer_start = first_link.start()
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else footer_start
        body = text[match.end() : end].strip("\n")
        sections.append((match.group("name"), match.group("date"), body))
    return preamble, sections, text[footer_start:]


def unreleased_notes(text: str) -> str:
    _, sections, _ = split_sections(text)
    name, _, body = sections[0]
    if name.lower() != "unreleased":
        raise SystemExit("the first section of CHANGELOG.md must be [Unreleased]")
    return body.strip()


def roll(text: str, version: str, date: str) -> str:
    preamble, sections, footer = split_sections(text)
    name, _, body = sections[0]
    if name.lower() != "unreleased":
        raise SystemExit("the first section of CHANGELOG.md must be [Unreleased]")
    if not body.strip():
        body = "_No notes were written for this release._"
    previous = sections[1][0] if len(sections) > 1 else None

    out = [preamble.rstrip("\n"), "", "## [Unreleased]", "", f"## [{version}] — {date}", "", body, ""]
    for other_name, other_date, other_body in sections[1:]:
        heading = f"## [{other_name}]" + (f" — {other_date}" if other_date else "")
        out += [heading, "", other_body, ""]

    links = [f"[Unreleased]: {REPO}/compare/v{version}...HEAD"]
    if previous:
        links.append(f"[{version}]: {REPO}/compare/v{previous}...v{version}")
    else:
        links.append(f"[{version}]: {REPO}/releases/tag/v{version}")
    for match in LINK.finditer(footer):
        if match.group("name").lower() not in {"unreleased", version}:
            links.append(match.group(0).strip())
    return "\n".join(out) + "\n" + "\n".join(links) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", nargs="?", help="version being released, e.g. 2.3.0")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--notes", type=Path, help="write the release notes to this file")
    parser.add_argument("--check", action="store_true", help="print the pending notes and change nothing")
    args = parser.parse_args()

    text = CHANGELOG.read_text(encoding="utf-8")
    notes = unreleased_notes(text)
    if args.check:
        print(notes or "(the Unreleased section is empty)")
        sys.exit(0 if notes else 1)
    if not args.version or not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("a version like 2.3.0 is required")

    updated = roll(text, args.version, args.date)
    CHANGELOG.write_text(updated, encoding="utf-8", newline="\n")
    if args.notes:
        args.notes.write_text(notes + "\n", encoding="utf-8", newline="\n")
    print(notes)


if __name__ == "__main__":
    main()
