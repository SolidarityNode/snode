# Documentation tooling

Locked environment for the documentation site: MkDocs (BSD-2-Clause), Material for MkDocs (MIT)
and mike (BSD-3-Clause). The site configuration is [`mkdocs.yml`](../../mkdocs.yml) at the
repository root; [`hooks.py`](hooks.py) adds the root files (CHANGELOG, CONTRIBUTING, AGENTS.md)
to the site and turns links to files outside `docs/` into links to GitHub.

```bash
make docs          # serve on http://127.0.0.1:8001 with live reload
make docs-build    # build into site/ with --strict (what CI runs)
```
