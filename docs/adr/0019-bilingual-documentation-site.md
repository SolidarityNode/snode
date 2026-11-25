# 0019. Bilingual documentation site: Greek user-facing pages with mkdocs-static-i18n

- Status: Proposed
- Date: 2026-11-26
- Deciders: maintainer (on the pull request)
- Related: ADR 0018; `docs/i18n/glossary.md`; `mkdocs.yml`, `tools/docs/hooks.py`, `scripts/docs_i18n.py`

## Context

The platform UI is in Greek and English, and its first users are municipal staff in Greece who are not developers. The documentation site (ADR 0018) was English only. The pages these users read (home, user guide, concepts, roadmap) need a Greek version that uses the same terms as the Greek UI (`docs/i18n/glossary.md`). The technical pages (architecture, ADRs, specs, open questions, paper revisions, data-processing notes, contributing, changelog) are read by developers and researchers and stay in English, with one source each. The site must keep working with mike versions (`dev`, `X.Y`, `latest`) and `mkdocs build --strict`, and no file under `docs/` may move.

## Options

1. **mkdocs-static-i18n (MIT), suffix layout**: `page.md` English, `page.el.md` Greek next to it, Greek served under `el/`. English is the fallback for pages without a Greek file. Integrates with the Material language switcher. One build, so it works with mike unchanged. Files do not move.
2. **Folder layout** (`docs/en/`, `docs/el/`) with the same plugin: moves every file, which breaks links from code, tests and `AGENTS.md`.
3. **A second MkDocs project for Greek**: two configurations and navigations to keep in step, two mike deployments, no shared switcher.
4. **Translation files (gettext/po)**: suited to software strings, awkward for prose and for reviewers who read the Greek page as a whole.

## Decision

Option 1: mkdocs-static-i18n 1.3.1 with the suffix layout, English as the default, the Material language switcher, and English fallback for pages kept in English. Each Greek page records the SHA-256 of its English source in its front matter (`translated_from_sha256`). `scripts/docs_i18n.py --check` (run by `make lint` and the docs workflow) warns about Greek pages whose source changed since, and fails if a user-guide page has no Greek version.

## Consequences

- `tools/docs/hooks.py` relies on two internals of the plugin: it adds the root pages (CHANGELOG, CONTRIBUTING, AGENTS.md) after the plugin's `on_files` with the plugin's file factory, and it rewrites the switcher links to relative ones, because the plugin makes the home-page links absolute from `site_url` and they would miss the mike version folder. Both are covered by `make docs-build`; recheck them when the plugin version changes.
- Changing an English user-facing page means updating its Greek page (`make docs-stamp PAGE=…`) or saying in the pull request that it is stale (AGENTS.md "Documentation rules").
- Material's search does not offer a Greek stemmer; Greek pages are searchable without stemming.
- Screenshots on Greek pages show the English UI except where a Greek screenshot exists; Greek UI screenshots for the user guide are a follow-up.
- The migration to Zensical (ADR 0018) must carry the bilingual site over, or replace this plugin with an equivalent; revisit then.
