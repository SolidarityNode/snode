#!/usr/bin/env python3
"""Fail if any dependency has a licence that is incompatible with AGPL-3.0 or unknown.

Usage:
    python check_licenses.py python          # inspects the running interpreter's environment
    pnpm licenses list --json --long | python3 check_licenses.py pnpm

Standard library only, so it runs inside any project environment. Policy (CLAUDE.md,
"Licensing"): permissive and weak-copyleft licences, GPL-3.0 and AGPL-3.0 are accepted;
anything else, including unknown licences, fails unless listed in EXCEPTIONS with a reason.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from importlib import metadata

# SPDX identifiers that may be combined into an AGPL-3.0 work.
ALLOWED = {
    "0BSD", "AFL-2.1", "Apache-2.0", "BlueOak-1.0.0", "BSD-2-Clause", "BSD-3-Clause",
    "CC-BY-3.0", "CC-BY-4.0", "CC0-1.0", "HPND", "ISC", "MIT", "MIT-0", "MPL-2.0", "PSF-2.0",
    "Python-2.0", "Python-2.0.1", "Unicode-3.0", "Unicode-DFS-2016", "Unlicense", "WTFPL",
    "Zlib",
    "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
}

# Common non-SPDX spellings found in package metadata.
ALIASES = {
    "MIT License": "MIT", "MIT license": "MIT", "Expat": "MIT",
    "BSD License": "BSD-3-Clause", "BSD": "BSD-3-Clause", "new BSD": "BSD-3-Clause",
    "BSD 3-Clause": "BSD-3-Clause", "3-Clause BSD License": "BSD-3-Clause",
    "Apache 2.0": "Apache-2.0", "Apache License 2.0": "Apache-2.0",
    "Apache Software License": "Apache-2.0", "Apache License, Version 2.0": "Apache-2.0",
    "ISC License (ISCL)": "ISC", "Python Software Foundation License": "PSF-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Library or Lesser General Public License (LGPL)": "LGPL-2.1-or-later",
    "GNU Affero General Public License v3": "AGPL-3.0-only",
    "GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0-or-later",
    "The Unlicense (Unlicense)": "Unlicense", "Public Domain": "CC0-1.0",
}

# Project packages and reviewed exceptions: name -> reason.
EXCEPTIONS: dict[str, str] = {
    "solidaritynode-core": "this project (AGPL-3.0-or-later)",
    "solidaritynode-backend": "this project (AGPL-3.0-or-later)",
}



def _normalise(token: str) -> str:
    token = token.strip().strip('"')
    return ALIASES.get(token, token)


def expression_allowed(expression: str) -> bool:
    """Return whether an SPDX-like expression is acceptable.

    ``OR`` needs one acceptable side; ``AND`` needs both. ``WITH`` exceptions are ignored
    (they only add permissions).
    """
    expression = _normalise(expression)
    if expression in ALLOWED:
        return True
    if not re.search(r"\b(AND|OR)\b", expression):
        return _normalise(expression.split(" WITH ")[0]) in ALLOWED
    # Evaluate with Python's boolean operators after mapping each licence to True/False.
    parts: list[str] = []
    for raw in re.split(r"(\(|\)|\bAND\b|\bOR\b)", expression):
        piece = raw.strip()
        if not piece:
            continue
        if piece in ("(", ")"):
            parts.append(piece)
        elif piece in ("AND", "OR"):
            parts.append(piece.lower())
        else:
            parts.append(str(_normalise(piece.split(" WITH ")[0]) in ALLOWED))
    try:
        return bool(eval(" ".join(parts), {"__builtins__": {}}, {}))  # noqa: S307 - only True/False/and/or/()
    except SyntaxError:
        return False


def _python_licence(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")
    ]
    classifiers = [c for c in classifiers if c != "OSI Approved"]
    if classifiers:
        return " OR ".join(_normalise(c) for c in classifiers)
    licence = (meta.get("License") or "").strip()
    if licence and "\n" not in licence and len(licence) < 80:
        return licence
    return "UNKNOWN"


def python_packages() -> Iterable[tuple[str, str]]:
    """Yield ``(name==version, licence)`` for the current environment."""
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        yield f"{name}=={dist.version}", _python_licence(dist)


def pnpm_packages(raw: str) -> Iterable[tuple[str, str]]:
    """Yield ``(name@versions, licence)`` from ``pnpm licenses list --json``."""
    data = json.loads(raw) if raw.strip() else {}
    for licence, packages in data.items():
        for package in packages:
            versions = ",".join(package.get("versions", []))
            yield f"{package['name']}@{versions}", licence


def main(argv: list[str]) -> int:
    """Run the check and print a report; return a process exit code."""
    if len(argv) != 2 or argv[1] not in ("python", "pnpm"):
        print(__doc__)
        return 2
    rows = list(python_packages() if argv[1] == "python" else pnpm_packages(sys.stdin.read()))
    failures = []
    for package, licence in sorted(rows):
        name = re.split(r"==|@(?=\d)", package)[0]
        if name in EXCEPTIONS or expression_allowed(licence):
            continue
        failures.append((package, licence))
    print(f"checked {len(rows)} {argv[1]} packages")
    for package, licence in failures:
        print(f"  NOT ALLOWED: {package}: {licence}")
    if failures:
        print("Review these licences (CLAUDE.md 'Licensing'); add a reasoned EXCEPTION if compatible.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
