# Data-processing conventions

Rules: [`data-processing/AGENTS.md`](../../data-processing/AGENTS.md). The root [`AGENTS.md`](../../AGENTS.md) also applies.

## A processing note for every processed dataset

Every processed dataset has a `DP-NNN` note copied from [`docs/data-processing/TEMPLATE.md`](../data-processing/TEMPLATE.md).

**Why:** a dataset is only as trustworthy as the record of how it was made.

**Example:** [`DP-001`](../data-processing/DP-001-synthetic-demo-dataset.md), the synthetic demo dataset.

## Relative paths, no data files

QGIS projects use relative paths. Commit no data files; only models, scripts, styles and projects.

**Why:** absolute paths break on every other machine, and data may be real or licensed (see "Data and privacy rules" in the root `AGENTS.md`).

## Exact QGIS calls in the note

Copy the exact QGIS calls from Processing → History into the note.

**Why:** the history holds the exact algorithm ids and parameters; a prose description cannot be re-run.

## QGIS is a preparation tool only

QGIS is never a runtime dependency of `core` or `backend`.

**Why:** the platform must install and run without a desktop GIS.
