# 0009. Geospatial data sources

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: OQ-22, `docs/data-sources.md`, Spec 00 §3 (networks, DEM)

## Context

Accessibility (Paper 1 §5) needs spatial units, population by group, facilities, per-mode transport networks (road, pedestrian, public transport) and a DEM. The first application uses Greek Local Communities (ΤΚ), but code must stay generic (OQ-22). Every third-party source must be attributed and its licence respected.

## Options to evaluate

1. **OpenStreetMap** (ODbL) via OSMnx (MIT) for road and pedestrian networks; attribution and share-alike obligations for derived databases.
2. **GTFS** feeds for public transport, where published (licence per operator).
3. **ELSTAT** census data and administrative boundaries for population by group (terms to check).
4. **Copernicus DEM** or EU-DEM for elevation (licence to check).
5. Facility registries from public bodies (licence to check).

## Questions to answer before deciding

- Which sources exist for the first study area, at what resolution and with which licences?
- How are ODbL share-alike obligations handled for derived travel-time matrices?
- Update frequency and versioning of inputs.
- Which synthetic equivalents do we ship in `data/synthetic/` for tests?

## Decision

Not decided.

## Consequences

To be written with the decision.
