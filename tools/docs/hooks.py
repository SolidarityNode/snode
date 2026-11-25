"""MkDocs hooks for the SolidarityNode documentation site (``mkdocs.yml``, ``hooks:``).

1. Root files that also belong on the site (CHANGELOG, CONTRIBUTING, AGENTS.md) are added as
   generated pages, so they keep one source at the repository root and are not copied.
2. Relative links are written for GitHub, relative to each file's place in the repository.
   On the site, a link to another documentation page stays a site link; a link to anything
   outside ``docs/`` (code, ``LICENSE``, ``core/AGENTS.md`` ...) becomes a link to the file
   on GitHub at ``DOCS_GIT_REF`` (default ``main``; the docs workflow sets the release tag).
3. The platform version from ``VERSION`` is shown in the footer (``extra.platform_version``).
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from typing import Any

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

REPO_URL = "https://github.com/SolidarityNode/snode"

# Repository file -> page path on the site.
ROOT_PAGES = {
    "CHANGELOG.md": "changelog.md",
    "CONTRIBUTING.md": "contributing/contributing.md",
    "AGENTS.md": "contributing/agents.md",
}

_LINK = re.compile(r"(!?\[[^\]\n]*\]\()(<?)([^)\s>]+)(>?)((?:\s+\"[^\"]*\")?\))")
_FENCE = re.compile(r"^(```|~~~)", re.MULTILINE)


def _root(config: MkDocsConfig) -> Path:
    return Path(config.config_file_path).resolve().parent


def _docs_prefix(config: MkDocsConfig) -> str:
    return Path(config.docs_dir).resolve().relative_to(_root(config)).as_posix()


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Expose the platform version and the git ref that GitHub links point to."""
    version = (_root(config) / "VERSION").read_text(encoding="utf-8").strip()
    config.extra["platform_version"] = version
    config.copyright = (
        f"SolidarityNode {version} · AGPL-3.0-or-later · synthetic data only in this repository"
    )
    return config


def on_files(files: Files, config: MkDocsConfig) -> Files:
    """Add the root files as generated pages."""
    root = _root(config)
    for source, dest in ROOT_PAGES.items():
        content = (root / source).read_text(encoding="utf-8")
        files.append(File.generated(config, dest, content=content))
    return files


def _repo_path(page: Page, config: MkDocsConfig) -> str:
    """Return the page's path in the repository (where its relative links were written)."""
    src = page.file.src_uri
    for source, dest in ROOT_PAGES.items():
        if src == dest:
            return source
    return f"{_docs_prefix(config)}/{src}"


def _rewrite(target: str, page: Page, config: MkDocsConfig, files: Files) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith(("#", "/")):
        return target
    path, sep, anchor = target.partition("#")
    if not path:
        return target
    base = posixpath.dirname(_repo_path(page, config))
    resolved = posixpath.normpath(posixpath.join(base, path))
    page_dir = posixpath.dirname(page.file.src_uri)
    prefix = _docs_prefix(config) + "/"

    site_path: str | None = None
    if resolved in ROOT_PAGES:
        site_path = ROOT_PAGES[resolved]
    elif resolved.startswith(prefix) and files.get_file_from_path(resolved[len(prefix) :]):
        site_path = resolved[len(prefix) :]
    if site_path is not None:
        return posixpath.relpath(site_path, page_dir or ".") + sep + anchor

    on_disk = _root(config) / resolved
    if not on_disk.exists() or resolved.startswith(".."):
        return target  # left alone: mkdocs --strict reports it
    kind = "tree" if on_disk.is_dir() else "blob"
    ref = os.environ.get("DOCS_GIT_REF", "main")
    return f"{REPO_URL}/{kind}/{ref}/{resolved}" + sep + anchor


def on_page_markdown(
    markdown: str, page: Page, config: MkDocsConfig, files: Files, **_: Any
) -> str:
    """Rewrite relative links outside fenced code blocks (see the module docstring).

    ``{{ platform_version }}`` is replaced by the version from ``VERSION``.
    """
    markdown = markdown.replace("{{ platform_version }}", config.extra["platform_version"])
    source = _repo_path(page, config)
    if source in ROOT_PAGES:  # edit and view the root file itself on GitHub
        page.edit_url = f"{REPO_URL}/edit/{os.environ.get('DOCS_GIT_REF', 'main')}/{source}"
    parts = _FENCE.split(markdown)
    # split() with one group yields: text, fence, text, fence, ...; inside = after an odd fence
    out: list[str] = []
    inside = False
    for index, part in enumerate(parts):
        if index % 2 == 1:  # the fence marker itself
            out.append(part)
            inside = not inside
            continue
        if inside:
            out.append(part)
        else:
            out.append(
                _LINK.sub(
                    lambda m: (
                        m.group(1)
                        + m.group(2)
                        + _rewrite(m.group(3), page, config, files)
                        + m.group(4)
                        + m.group(5)
                    ),
                    part,
                )
            )
    return "".join(out)
