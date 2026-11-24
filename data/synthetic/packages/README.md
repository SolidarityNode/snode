# Synthetic demo data packages

> **SYNTHETIC.** Built from the demo dataset in [`../demo/`](../demo/README.md) for tests and
> UAT only. Quality labels and coverage statuses are invented.

| Directory | Version | Content |
| --- | --- | --- |
| `demo-1.0.0/` | 1.0.0 | Municipality M-A onboarded (facilities verified). Neighbour M-B only as buffer: boundaries, estimated population and network; facilities missing, so units of A next to B carry an edge-effect warning. |
| `demo-1.1.0/` | 1.1.0 | M-B onboarded: cross-border facility F4 added (verified); F2 capacity corrected (S-SD throughput 100 → 90); F3 closed (`valid_to` 2026-12-01). |

Format: v0.1 data package (ADR 0013): `manifest.json` (package id, study area, semantic
version, schema version, CRS, buffer, coverage per municipality and layer, files with SHA-256
checksums, sources, `DP-NNN` notes, changelog) plus GeoJSON layers and CSV tables.

Import with `make import-package PKG=data/synthetic/packages/demo-1.1.0` or from the Admin
screen. Rebuild with `python3 scripts/build_demo_packages.py` (byte-for-byte reproducible;
processing note [DP-002](../../../docs/data-processing/DP-002-synthetic-demo-packages.md)).
