# Synthetic demo data packages

> **SYNTHETIC.** Built from the demo dataset in [`../demo/`](../demo/README.md) for tests and
> UAT only. Quality labels and coverage statuses are invented.

| Directory | Version | Content |
| --- | --- | --- |
| `demo-1.0.0/` | 1.0.0 | Municipality M-A onboarded (facilities `verified_by_municipality`). Neighbour M-B only as buffer: boundaries, estimated population and network; facilities missing, so units of A next to B carry an edge-effect warning. |
| `demo-1.1.0/` | 1.1.0 | M-B onboarded: cross-border facility F4 added (`verified_by_municipality`); F2 capacity corrected (S-SD throughput 100 → 90); F3 closed (`valid_to` 2026-12-01). |

Format: data package schema 2.0 (ADR 0013): `manifest.json` (package id, study area, semantic
version, schema version, CRS, buffer, coverage per municipality and layer, layers with licence
and attribution, files with SHA-256 checksums, sources, `DP-NNN` notes, changelog), one
GeoPackage `layers.gpkg` (one table per layer, EPSG:2100) and CSV tables.

CSV dialect: UTF-8, comma delimiter, dot as decimal separator, one header row. Files saved by a
Greek-locale spreadsheet (semicolons, comma decimals, Windows-1253) are refused with a message;
save them as "CSV UTF-8 (comma delimited)" with a dot as decimal separator.

Licences: every layer of these packages is synthetic, AGPL-3.0-or-later, attributed to the
generator script. Real packages carry each layer's own licence (for example ODbL for
OpenStreetMap-derived layers) and need legal review before distribution.

Import with `make import-package PKG=data/synthetic/packages/demo-1.1.0` or from the Admin
screen; make an earlier version active again with `make activate-version VERSION=1.0.0` or the
Admin screen. Rebuild with `python3 scripts/build_demo_packages.py` (byte-for-byte reproducible;
processing note [DP-002](../../../docs/data-processing/DP-002-synthetic-demo-packages.md)).
