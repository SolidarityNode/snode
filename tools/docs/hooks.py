"""MkDocs hooks for the SolidarityNode documentation site (``mkdocs.yml``, ``hooks:``).

1. Root files that also belong on the site (CHANGELOG, CONTRIBUTING, AGENTS.md) are added as
   generated pages, so they keep one source at the repository root and are not copied.
2. Relative links are written for GitHub, relative to each file's place in the repository.
   On the site, a link to another documentation page stays a site link; a link to anything
   outside ``docs/`` (code, ``LICENSE``, ``core/AGENTS.md`` ...) becomes a link to the file
   on GitHub at ``DOCS_GIT_REF`` (default ``main``; the docs workflow sets the release tag).
3. The platform version from ``VERSION`` is shown in the footer (``extra.platform_version``).
   The version banners (``tools/docs/overrides/main.html``, docs/releasing.md) get
   ``extra.docs_channel`` (``release`` when ``DOCS_GIT_REF`` is a release tag ``vX.Y.Z``, as the
   docs workflow sets it for tags; ``dev`` otherwise, including local builds) and
   ``extra.docs_release`` (``vX.Y`` from ``VERSION``).
4. Bilingual site (mkdocs-static-i18n, ``page.md`` English, ``page.el.md`` Greek, served under
   ``el/``). The plugin rebuilds every file from ``docs/`` once per language, so the root pages
   of (1) are added after it and made into its kind of file. The language switcher links are
   made relative to the page: the plugin's links on the home pages are absolute from
   ``site_url`` and would miss the mike version folder (``/snode/dev/el/``).
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from typing import Any

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import event_priority
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
    ref = os.environ.get("DOCS_GIT_REF", "main")
    config.extra["docs_channel"] = "release" if re.fullmatch(r"v\d+\.\d+\.\d+", ref) else "dev"
    config.extra["docs_release"] = "v" + ".".join(version.split(".")[:2])
    config.copyright = (
        f"SolidarityNode {version} · AGPL-3.0-or-later · synthetic data only in this repository"
    )
    return config


def _i18n(config: MkDocsConfig) -> Any:
    """Return the mkdocs-static-i18n plugin instance, or None when it is not configured."""
    return config.plugins.get("i18n")


@event_priority(-110)  # after mkdocs-static-i18n (-100), which rebuilds files from docs/
def on_files(files: Files, config: MkDocsConfig) -> Files:
    """Add the root files as generated pages (in the language being built, see (4))."""
    root = _root(config)
    i18n = _i18n(config)
    for source, dest in ROOT_PAGES.items():
        content = (root / source).read_text(encoding="utf-8")
        file = File.generated(config, dest, content=content)
        if i18n is not None:
            from mkdocs_static_i18n.suffix import create_i18n_file

            generated_by = file.generated_by
            file = create_i18n_file(
                file, i18n.current_language, i18n.default_language, i18n.all_languages, config
            )
            file.content_string = content  # the plugin's copy points into docs/; keep the text
            file.generated_by = generated_by
        files.append(file)
    return files


@event_priority(0)  # after mkdocs-static-i18n sets its own links (50)
def on_page_context(
    context: dict[str, Any], page: Page, config: MkDocsConfig, **_: Any
) -> dict[str, Any]:
    """Point each language switcher entry at the same page in that language.

    The link is relative to the site root of the version being built; the theme makes it
    relative to the page. Every page exists in every language (English is the fallback), so
    the counterpart of ``el/x/`` is ``x/`` and the reverse.
    """
    i18n = _i18n(config)
    alternates = getattr(config.extra, "alternate", None) or config.extra.get("alternate")
    if i18n is None or not alternates:
        return context
    url = page.url
    current, default = i18n.current_language, i18n.default_language
    if current != default and url.startswith(f"{current}/"):
        url = url[len(current) + 1 :]
    links = []
    for alternate in alternates:
        lang = alternate["lang"]
        target = url if lang == default else f"{lang}/{url}"
        links.append({**alternate, "link": target or "./"})
    # The plugin sets ``config.extra.alternate`` as an attribute, which the theme reads first.
    config.extra["alternate"] = links
    config.extra.alternate = links
    return context


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
