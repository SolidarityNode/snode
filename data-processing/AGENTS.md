# AGENTS.md (data-processing)

Applies to files under data-processing/, in addition to the root AGENTS.md. If the two conflict, the root wins; report the conflict.

Explanations and examples: [docs/conventions/data-processing.md](../docs/conventions/data-processing.md).

## Rules

- Every processed dataset has a `DP-NNN` note copied from `docs/data-processing/TEMPLATE.md`.
- QGIS projects use relative paths. Commit no data files; only models, scripts, styles and projects.
- Copy the exact QGIS calls from Processing → History into the note.
- QGIS is never a runtime dependency of `core` or `backend`.
