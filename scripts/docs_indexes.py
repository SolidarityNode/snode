#!/usr/bin/env python3
"""Generate the documentation indexes from their single sources, or check they are current.

Usage:
    python3 scripts/docs_indexes.py           # rewrite the generated blocks
    python3 scripts/docs_indexes.py --check   # exit 1 if a block is out of date (CI, `make lint`)

Generated blocks sit between ``<!-- BEGIN GENERATED: <name> ... -->`` and
``<!-- END GENERATED: <name> -->`` markers; everything outside them is written by hand.

| Block | Written into | Source |
| --- | --- | --- |
| ``adr-index`` | ``docs/adr/README.md`` | the header lines of every ``docs/adr/NNNN-*.md`` |
| ``specs-index`` | ``docs/specs/README.md`` | the title and ``Status:`` line of each spec file |
| ``oq-counts`` | ``README.md``, ``docs/index.md``, ``docs/specs/README.md`` | the summary table of ``docs/specs/open-questions.md`` |
| ``platform-version`` | ``README.md`` (under the logo) | ``VERSION`` |

``--check`` also enforces the diagram rule (AGENTS.md "Documentation rules"): no diagram files
(``.svg``, ``.drawio``, ``.puml``, ...) and no non-Mermaid diagram code blocks in the docs.
The logo in ``docs/assets/brand/`` is not a diagram and is exempt.

Standard library only.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
SPECS_DIR = ROOT / "docs" / "specs"
OPEN_QUESTIONS = SPECS_DIR / "open-questions.md"
VERSION_FILE = ROOT / "VERSION"
BRAND_DIR = ROOT / "docs" / "assets" / "brand"  # logo files, not diagrams

_BLOCK = re.compile(
    r"(?P<indent>[ \t]*)(?P<begin><!-- BEGIN GENERATED: (?P<name>[a-z-]+)[^>]*-->\n)"
    r"(?P<body>.*?)(?P<end>[ \t]*<!-- END GENERATED: (?P=name) -->)",
    re.DOTALL,
)


def _field(text: str, name: str) -> str:
    match = re.search(rf"^- {name}:\s*(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def adr_index() -> str:
    """Return the ADR table: number, title, status, date and the OQ-n each ADR relates to."""
    rows = [
        "| ADR | Title | Status | Date | Related open questions |",
        "| --- | --- | --- | --- | --- |",
    ]
    for path in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        heading = re.search(r"^# (\d{4})\.\s*(.+)$", text, re.MULTILINE)
        if not heading:
            raise SystemExit(f"{path.relative_to(ROOT)}: first heading must be '# NNNN. Title'")
        number, title = heading.groups()
        status = _field(text, "Status") or "(missing)"
        date = _field(text, "Date").split(" ")[0] or "(missing)"
        related = _field(text, "Related")
        oqs = sorted(set(re.findall(r"OQ-\d+", related)), key=lambda q: int(q[3:]))
        rows.append(f"| [{number}]({path.name}) | {title} | {status} | {date} | {', '.join(oqs)} |")
    return "\n".join(rows) + "\n"


def specs_index() -> str:
    """Return the table of specification files with their title and stated status."""
    rows = ["| File | Title | State |", "| --- | --- | --- |"]
    paths = [p for p in sorted(SPECS_DIR.glob("*.md")) if p.name != "README.md"]
    paths.append(SPECS_DIR / "source" / "README.md")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", text, re.MULTILINE)
        head = "\n".join(text.splitlines()[:8])  # a file's own status is stated at the top
        status = re.search(r"\*\*Status:\s*([^*]+?)\.?\*\*", head) or re.search(
            r"^>\s*Status:\s*(.+?)\.?$", head, re.MULTILINE
        )
        state = status.group(1).strip() if status else "living document"
        if path == OPEN_QUESTIONS:
            state = oq_counts().strip()
        rel = path.relative_to(SPECS_DIR).as_posix()
        rows.append(f"| [`{rel}`]({rel}) | {title.group(1) if title else rel} | {state} |")
    return "\n".join(rows) + "\n"


def oq_status_counts() -> Counter[str]:
    """Count the open questions by status group, from the summary table (the single source)."""
    text = OPEN_QUESTIONS.read_text(encoding="utf-8")
    counts: Counter[str] = Counter()
    for status in re.findall(r"^\| OQ-\d+ \|[^|]*\| ([^|]+) \|$", text, re.MULTILINE):
        status = status.strip().lower()
        if status.startswith("decided"):
            counts["decided"] += 1
        elif status.startswith("proposed"):
            counts["proposed"] += 1
        elif status.startswith("open"):
            counts["open"] += 1
        else:  # "partly decided", "approach decided, values open"
            counts["partly decided"] += 1
    if not counts:
        raise SystemExit("open-questions.md: no summary table rows found")
    return counts


def oq_counts() -> str:
    """Return one sentence with the open-question counts."""
    c = oq_status_counts()
    total = sum(c.values())
    return (
        f"{total} questions: **{c['decided']} decided**, {c['partly decided']} partly decided, "
        f"{c['proposed']} proposed, **{c['open']} open**.\n"
    )


def platform_version() -> str:
    """Return the product name and the platform version from VERSION (HTML: it sits in a <p>)."""
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    return f"<strong>SN Kintsugi</strong> · version {version}\n"


GENERATORS: dict[str, Callable[[], str]] = {
    "adr-index": adr_index,
    "specs-index": specs_index,
    "oq-counts": oq_counts,
    "platform-version": platform_version,
}
TARGETS = [
    ROOT / "README.md",
    ROOT / "docs" / "index.md",
    ADR_DIR / "README.md",
    SPECS_DIR / "README.md",
]


def render(text: str) -> str:
    """Return ``text`` with every generated block replaced by its current content."""

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in GENERATORS:
            raise SystemExit(f"unknown generated block {name!r}")
        indent = match.group("indent")
        body = "".join(
            indent + line if line.strip() else line for line in GENERATORS[name]().splitlines(True)
        )
        return indent + match.group("begin") + body + indent + match.group("end").lstrip()

    return _BLOCK.sub(replace, text)


DIAGRAM_FILES = (".svg", ".drawio", ".dio", ".puml", ".plantuml", ".mmd", ".excalidraw", ".vsdx")
_OTHER_DIAGRAM_FENCE = re.compile(
    r"^\s*(```|~~~)\s*(plantuml|puml|dot|graphviz|ditaa|d2|svgbob)\b", re.M
)


def diagram_problems() -> list[str]:
    """Return violations of the Mermaid-only diagram rule in README.md and docs/."""
    problems = [
        f"{p.relative_to(ROOT)}: diagram file; write diagrams as Mermaid code blocks"
        for p in sorted((ROOT / "docs").rglob("*"))
        if p.suffix.lower() in DIAGRAM_FILES and BRAND_DIR not in p.parents
    ]
    for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        if _OTHER_DIAGRAM_FENCE.search(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(ROOT)}: non-Mermaid diagram block; use Mermaid")
    return problems


def main(argv: list[str]) -> int:
    """Rewrite or check every target file; return the exit code."""
    check = "--check" in argv
    stale = []
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        new = render(text)
        if new != text:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(new, encoding="utf-8")
    problems = diagram_problems() if check else []
    for problem in problems:
        print(problem)
    if check and (stale or problems):
        for path in stale:
            print(f"out of date: {path}")
        if stale:
            print("Run `make docs-generate` and commit the result.")
        return 1
    print("generated indexes " + ("checked" if check else "written") + f" ({len(TARGETS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
