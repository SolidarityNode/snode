#!/usr/bin/env python3
"""Generate docs/architecture/dependencies.md from the lock files, or check that it is current.

Usage (after `make setup` and `make docs-setup`, which install the locked environments):
    python3 scripts/deps_report.py           # write the report
    python3 scripts/deps_report.py --check   # exit 1 if it is out of date or a licence is not allowed

Sources:
- Python: ``core/uv.lock``, ``backend/uv.lock`` and ``tools/docs/uv.lock`` give the packages,
  versions and which are runtime or dev-only (transitive closure from each project); the
  licence comes from the installed metadata in each project's ``.venv`` (as in
  ``scripts/check_licenses.py``, whose allowed list and exceptions are reused).
- JavaScript: ``frontend/pnpm-lock.yaml`` through ``pnpm licenses list --json --long``, with
  ``--prod`` for the runtime set.
- Container images: ``compose.yaml``, the Containerfiles and the Makefile, with the reviewed
  licence table ``IMAGES`` below (images are separate programs, not linked into the project).

Standard library only (Python 3.11+ for ``tomllib``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_licenses import EXCEPTIONS, _python_licence, expression_allowed  # noqa: E402

OUTPUT = ROOT / "docs" / "architecture" / "dependencies.md"
PYTHON_PROJECTS = {
    "core": ROOT / "core",
    "backend": ROOT / "backend",
    "docs": ROOT / "tools" / "docs",
}
FRONTEND = ROOT / "frontend"

# Reviewed licences of container images (repository without tag -> (licence, note)).
# A new image fails the check until it is added here.
IMAGES: dict[str, tuple[str, str]] = {
    "docker.io/postgis/postgis": (
        "PostgreSQL; PostGIS GPL-2.0-or-later; image MIT",
        "database server (separate program)",
    ),
    "docker.io/library/python": (
        "PSF-2.0; Debian base packages under their own licences",
        "backend and worker runtime",
    ),
    "ghcr.io/astral-sh/uv": ("MIT OR Apache-2.0", "build stage only (backend image)"),
    "docker.io/library/node": (
        "MIT; Alpine base packages under their own licences",
        "build stage only (frontend image)",
    ),
    "docker.io/nginxinc/nginx-unprivileged": (
        "nginx BSD-2-Clause; image Apache-2.0",
        "frontend runtime (static files, /api proxy)",
    ),
    "mcr.microsoft.com/playwright": ("Apache-2.0", "end-to-end tests only (make test-e2e)"),
}

_SKIP_MARKER = re.compile(
    r"(sys_platform|platform_system|os_name)\s*==\s*'(win32|Windows|darwin|nt|cygwin)'"
)


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _closure(packages: dict[str, dict], roots: list[dict]) -> set[str]:
    """Return the names reachable from ``roots`` (lock dependency entries), with extras."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        dep = stack.pop()
        if _SKIP_MARKER.search(dep.get("marker", "")):
            continue
        name = _norm(dep["name"])
        pkg = packages.get(name)
        if pkg is None:
            continue
        extras = tuple(dep.get("extra", []))
        key = name + "[" + ",".join(extras) + "]"
        if key in seen:
            continue
        seen.add(key)
        stack.extend(pkg.get("dependencies", []))
        for extra in extras:
            stack.extend(pkg.get("optional-dependencies", {}).get(extra, []))
    return {k.split("[")[0] for k in seen}


def python_rows() -> tuple[dict[tuple[str, str], set[str]], dict[tuple[str, str], str]]:
    """Return ``{(name, version): {usage}}`` and ``{(name, version): licence}``."""
    usage: dict[tuple[str, str], set[str]] = defaultdict(set)
    licences: dict[tuple[str, str], str] = {}
    for project, path in PYTHON_PROJECTS.items():
        lock = tomllib.loads((path / "uv.lock").read_text(encoding="utf-8"))
        packages = {_norm(p["name"]): p for p in lock["package"]}
        root = next(
            p
            for p in lock["package"]
            if p.get("source", {}).get("editable") == "."
            or p.get("source", {}).get("virtual") == "."
        )
        runtime = _closure(packages, root.get("dependencies", []))
        dev_roots = [d for group in root.get("dev-dependencies", {}).values() for d in group]
        dev = _closure(packages, dev_roots) - runtime
        site = sorted((path / ".venv" / "lib").glob("python*/site-packages"))
        if not site:
            raise SystemExit(
                f"{path.relative_to(ROOT)}/.venv missing: run `make setup docs-setup` first"
            )
        installed = {
            _norm(d.metadata["Name"]): d for d in metadata.distributions(path=[str(site[0])])
        }
        for names, kind in ((runtime, "runtime"), (dev, "dev")):
            for name in names:
                if name.startswith("solidaritynode-"):
                    continue
                version = packages[name].get("version", "")
                key = (name, version)
                label = "docs tooling" if project == "docs" else project
                usage[key].add(label if kind == "runtime" and project != "docs" else f"dev:{label}")
                dist = installed.get(name)
                if dist is None:
                    raise SystemExit(f"{name} {version} is locked for {project} but not installed")
                licences[key] = _python_licence(dist)
    return usage, licences


def js_rows() -> tuple[dict[tuple[str, str], set[str]], dict[tuple[str, str], str]]:
    """Return the same mappings for the frontend, from ``pnpm licenses list``."""
    pnpm = os.environ.get("PNPM", "pnpm")

    def listing(*extra: str) -> dict[tuple[str, str], str]:
        out = subprocess.run(
            [pnpm, "licenses", "list", "--json", "--long", *extra],
            cwd=FRONTEND,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        data = json.loads(out) if out.strip() else {}
        return {
            (pkg["name"], version): licence
            for licence, pkgs in data.items()
            for pkg in pkgs
            for version in pkg.get("versions", [])
        }

    every = listing()
    prod = listing("--prod")
    usage = {key: {"frontend" if key in prod else "dev:frontend"} for key in every}
    return usage, every


def image_rows() -> list[tuple[str, str, str, str]]:
    """Return ``(image, tag, licence, use)`` for every container image referenced."""
    refs: set[str] = set()
    for path in [ROOT / "compose.yaml", *ROOT.glob("*/Containerfile")]:
        text = path.read_text(encoding="utf-8")
        refs.update(re.findall(r"^\s*image:\s*(\S+)", text, re.MULTILINE))
        refs.update(re.findall(r"^FROM\s+(\S+)", text, re.MULTILINE))
    refs.update(
        re.findall(r"^PLAYWRIGHT_IMAGE \?= (\S+)", (ROOT / "Makefile").read_text(), re.MULTILINE)
    )
    rows = []
    for ref in sorted(refs):
        if ref.startswith("localhost/"):
            continue  # this project's own images
        repo, _, tag = ref.rpartition(":")
        if repo not in IMAGES:
            raise SystemExit(
                f"container image {repo} has no reviewed licence: add it to IMAGES in {__file__}"
            )
        rows.append((repo, tag, *IMAGES[repo]))
    return rows


def _used_by(labels: set[str]) -> str:
    runtime = sorted(lab for lab in labels if not lab.startswith("dev:"))
    dev = sorted(lab[4:] for lab in labels if lab.startswith("dev:") and lab[4:] not in runtime)
    parts = []
    if runtime:
        parts.append(", ".join(runtime))
    if dev:
        parts.append("dev only: " + ", ".join(dev))
    return "; ".join(parts)


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def render() -> tuple[str, list[str]]:
    """Return the Markdown report and the list of licence problems."""
    problems: list[str] = []
    sections = []
    for title, (usage, licences) in (
        ("Python packages", python_rows()),
        ("JavaScript packages", js_rows()),
    ):
        lines = [
            f"## {title}",
            "",
            "| Package | Version | Licence | Used by |",
            "| --- | --- | --- | --- |",
        ]
        for name, version in sorted(usage, key=lambda k: (k[0].lower(), k[1])):
            licence = licences[(name, version)]
            if not (name in EXCEPTIONS or expression_allowed(licence)):
                problems.append(f"{name} {version}: {licence}")
            lines.append(
                f"| {name} | {version} | {_escape(licence)} | {_used_by(usage[(name, version)])} |"
            )
        sections.append("\n".join(lines))
    lines = [
        "## Container images",
        "",
        "| Image | Tag | Licence | Use |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| `{r}` | `{t}` | {lic} | {u} |" for r, t, lic, u in image_rows()]
    sections.append("\n".join(lines))
    header = """# Dependencies

<!-- GENERATED by scripts/deps_report.py (make deps-report). Do not edit by hand; CI checks it. -->

> Generated from `core/uv.lock`, `backend/uv.lock`, `tools/docs/uv.lock` and `frontend/pnpm-lock.yaml`, with licences from the installed package metadata, plus the container images. CI fails when this page is out of date or a licence is not on the allowed list of `scripts/check_licenses.py` (AGENTS.md, "Licensing": AGPL-3.0-compatible licences only).

**Used by**: the component that needs the package at run time (`core` packages are also in the `backend` image); **dev only**: needed only to lint, test, build or document. A package is listed once per version. Generated on Linux x86-64, as in CI; platform-specific optional packages differ on other systems.
"""
    return header + "\n" + "\n\n".join(sections) + "\n", problems


def main(argv: list[str]) -> int:
    """Write or check the report; return the exit code."""
    text, problems = render()
    for problem in problems:
        print(f"licence NOT ALLOWED: {problem}")
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(
                f"{OUTPUT.relative_to(ROOT)} is out of date: run `make deps-report` and commit it"
            )
            return 1
    else:
        OUTPUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
