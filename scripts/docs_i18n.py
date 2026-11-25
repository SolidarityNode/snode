#!/usr/bin/env python3
"""Check that the Greek pages of the documentation site follow their English sources.

Usage:
    python3 scripts/docs_i18n.py --check            # `make lint`, `make docs-check`, CI
    python3 scripts/docs_i18n.py --stamp PAGE.el.md # after updating a Greek page

The site is bilingual (mkdocs-static-i18n, suffix layout): ``docs/x.md`` is English and
``docs/x.el.md`` its Greek translation. Each Greek page starts with YAML front matter that
records the SHA-256 of the English file it was translated from::

    ---
    translated_from_sha256: <64 hex characters>
    ---

``--check``:

- **warns** (exit 0) about Greek pages whose English source changed since (the hash differs),
  listing them, so the change can be translated or noted as stale in the pull request;
- **fails** (exit 1) when a page that must be in Greek has no Greek file (every page of
  ``docs/user-guide/``), when a Greek page has no English source, or when its front matter has
  no valid ``translated_from_sha256``.

``--stamp`` writes the current hash of the English source into the given Greek pages. Run it
only after the Greek text matches the English page again.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SUFFIX = ".el.md"
FIELD = "translated_from_sha256"
# English pages that must have a Greek version (globs relative to docs/).
REQUIRED = ["user-guide/*.md"]

_FRONT_MATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
_HASH_LINE = re.compile(rf"^{FIELD}:[ \t]*(?P<value>\S*)[ \t]*$", re.MULTILINE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def english_source(greek: Path) -> Path:
    """Return the English page that ``greek`` (``x.el.md``) translates (``x.md``)."""
    return greek.with_name(greek.name[: -len(SUFFIX)] + ".md")


def sha256(path: Path) -> str:
    """Return the SHA-256 of the file's bytes, as lowercase hex."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_hash(greek: Path) -> str | None:
    """Return the hash in the page's front matter, or None if there is none."""
    match = _FRONT_MATTER.match(greek.read_text(encoding="utf-8"))
    if not match:
        return None
    field = _HASH_LINE.search(match.group("body"))
    return field.group("value").strip("'\"") if field else None


def greek_pages() -> list[Path]:
    """Return every Greek page under docs/, sorted."""
    return sorted(DOCS.rglob(f"*{SUFFIX}"))


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def check() -> int:
    """Report stale Greek pages (warning) and missing or malformed ones (error)."""
    errors: list[str] = []
    stale: list[tuple[Path, Path]] = []
    for greek in greek_pages():
        source = english_source(greek)
        if not source.exists():
            errors.append(f"{_rel(greek)}: no English source {_rel(source)}")
            continue
        recorded = recorded_hash(greek)
        if recorded is None or not _SHA256.match(recorded):
            errors.append(
                f"{_rel(greek)}: front matter needs '{FIELD}: <SHA-256 of {_rel(source)}>' "
                f"(python3 scripts/docs_i18n.py --stamp {_rel(greek)})"
            )
        elif recorded != sha256(source):
            stale.append((greek, source))

    for pattern in REQUIRED:
        for source in sorted(DOCS.glob(pattern)):
            if source.name.endswith(SUFFIX):
                continue
            greek = source.with_name(source.stem + SUFFIX)
            if not greek.exists():
                errors.append(f"{_rel(source)}: no Greek version {_rel(greek)}")

    if stale:
        print(
            f"warning: {len(stale)} Greek page(s) older than their English source "
            "(update the translation and --stamp it, or say in the pull request that it is stale):",
            file=sys.stderr,
        )
        for greek, source in stale:
            print(f"  {_rel(greek)}  (source {_rel(source)} changed)", file=sys.stderr)
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(
                    f"::warning file={_rel(greek)}::English source {_rel(source)} changed since "
                    "this translation"
                )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"Greek pages checked ({len(greek_pages())} files, {len(stale)} stale)")
    return 0


def stamp(pages: list[str]) -> int:
    """Write the current hash of each page's English source into its front matter."""
    for name in pages:
        greek = Path(name).resolve()
        if not greek.name.endswith(SUFFIX) or not greek.exists():
            print(f"error: {name}: not an existing *{SUFFIX} page", file=sys.stderr)
            return 1
        source = english_source(greek)
        if not source.exists():
            print(f"error: {name}: no English source {_rel(source)}", file=sys.stderr)
            return 1
        line = f"{FIELD}: {sha256(source)}"
        text = greek.read_text(encoding="utf-8")
        match = _FRONT_MATTER.match(text)
        if match is None:
            text = f"---\n{line}\n---\n\n{text}"
        elif _HASH_LINE.search(match.group("body")):
            body = _HASH_LINE.sub(line, match.group("body"), count=1)
            text = f"---\n{body}\n---\n" + text[match.end() :]
        else:
            text = f"---\n{match.group('body')}\n{line}\n---\n" + text[match.end() :]
        greek.write_text(text, encoding="utf-8")
        print(f"stamped {_rel(greek)} from {_rel(source)}")
    return 0


def main() -> int:
    """Run --check or --stamp; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="report stale and missing pages")
    group.add_argument("--stamp", nargs="+", metavar="PAGE", help="record the source hash")
    args = parser.parse_args()
    return check() if args.check else stamp(args.stamp)


if __name__ == "__main__":
    sys.exit(main())
