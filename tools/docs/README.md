# Documentation tooling

Locked environment for the documentation site: MkDocs (BSD-2-Clause), Material for MkDocs (MIT),
mike (BSD-3-Clause) and mkdocs-static-i18n (MIT). The site configuration is
[`mkdocs.yml`](../../mkdocs.yml) at the repository root; [`hooks.py`](hooks.py) adds the root files
(CHANGELOG, CONTRIBUTING, AGENTS.md) to the site, turns links to files outside `docs/` into links
to GitHub, and keeps the language switcher working under mike.

The site is bilingual ([ADR 0019](../../docs/adr/0019-bilingual-documentation-site.md)):
`page.el.md` is the Greek version of `page.md` and is served under `el/`; pages without a Greek
file appear in English on the Greek site. `make docs-stamp PAGE=docs/<page>.el.md` records that a
Greek page matches its English source; `make lint` warns about stale ones.

```bash
make docs          # serve on http://127.0.0.1:8001 with live reload
make docs-build    # build into site/ with --strict (what CI runs)
```
