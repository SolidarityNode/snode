#!/usr/bin/env python3
"""Keep the platform version in one place: the file ``VERSION`` at the repository root.

Usage:
    python3 scripts/version.py              # print the version
    python3 scripts/version.py sync         # write it into every manifest listed below
    python3 scripts/version.py check        # exit 1 if a manifest differs (CI, `make lint`)

``VERSION`` is the single source (docs/releasing.md). It reaches the backend and core through
their package metadata (``__version__``, ``/version``, the frontend footer and the run
reproducibility record), the frontend through ``package.json``, and the documentation site
through ``tools/docs/hooks.py``. After ``sync``, run ``uv lock`` in ``core/`` and ``backend/``
(``make version-sync`` does both). Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

PYPROJECTS = [ROOT / "core" / "pyproject.toml", ROOT / "backend" / "pyproject.toml"]
PACKAGE_JSON = ROOT / "frontend" / "package.json"
# uv.lock files record the version of the project packages they contain.
LOCKS = {
    ROOT / "core" / "uv.lock": ["solidaritynode-core"],
    ROOT / "backend" / "uv.lock": ["solidaritynode-backend", "solidaritynode-core"],
}
_PYPROJECT_VERSION = re.compile(r'^(version\s*=\s*")([^"]*)(")', re.MULTILINE)


def read_version() -> str:
    """Return the platform version from ``VERSION`` (semantic versioning)."""
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER.match(version):
        raise SystemExit(f"VERSION: {version!r} is not a semantic version (x.y.z)")
    return version


def _lock_versions(text: str, names: list[str]) -> dict[str, str]:
    found = {}
    for name in names:
        match = re.search(rf'^name = "{re.escape(name)}"\nversion = "([^"]*)"', text, re.MULTILINE)
        found[name] = match.group(1) if match else "<missing>"
    return found


def manifest_versions() -> dict[str, str]:
    """Return ``{manifest label: version}`` for every place that must equal ``VERSION``."""
    result: dict[str, str] = {}
    for path in PYPROJECTS:
        match = _PYPROJECT_VERSION.search(path.read_text(encoding="utf-8"))
        result[str(path.relative_to(ROOT))] = match.group(2) if match else "<missing>"
    result[str(PACKAGE_JSON.relative_to(ROOT))] = json.loads(
        PACKAGE_JSON.read_text(encoding="utf-8")
    )["version"]
    for path, names in LOCKS.items():
        for name, version in _lock_versions(path.read_text(encoding="utf-8"), names).items():
            result[f"{path.relative_to(ROOT)} ({name})"] = version
    return result


def sync(version: str) -> None:
    """Write ``version`` into the pyproject files and ``package.json`` (not the locks)."""
    for path in PYPROJECTS:
        text = path.read_text(encoding="utf-8")
        path.write_text(_PYPROJECT_VERSION.sub(rf"\g<1>{version}\g<3>", text, count=1), "utf-8")
    text = PACKAGE_JSON.read_text(encoding="utf-8")
    PACKAGE_JSON.write_text(
        re.sub(r'^(  "version": ")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1, flags=re.M),
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    """Command-line entry point; returns the exit code."""
    version = read_version()
    command = argv[1] if len(argv) > 1 else "print"
    if command == "print":
        print(version)
        return 0
    if command == "sync":
        sync(version)
        print(f"version {version} written; now run `uv lock` in core/ and backend/")
        return 0
    if command == "check":
        wrong = {k: v for k, v in manifest_versions().items() if v != version}
        for label, found in wrong.items():
            print(f"version mismatch: {label} has {found}, VERSION has {version}")
        if wrong:
            print("Run `make version-sync` (scripts/version.py sync, then uv lock).")
            return 1
        print(f"version {version}: all manifests agree")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
