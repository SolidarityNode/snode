# 0007. Frontend map library

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: README "Planned capabilities"; `frontend/`

## Context

The frontend will show indicators per spatial unit, group and service, with uncertainty (AGENTS.md invariant 6), and vulnerability maps at reference scenarios (OQ-16). No map library is installed yet.

## Options to evaluate

1. **MapLibre GL JS** (BSD-3-Clause): vector tiles, WebGL, styling; good for many polygons.
2. **Leaflet** (BSD-2-Clause): simple, raster-first, large plugin ecosystem.
3. **OpenLayers** (BSD-2-Clause): full GIS feature set, heavier API.
4. **deck.gl** (MIT) on top of MapLibre for large data layers.

## Questions to answer before deciding

- Basemap source and its licence/attribution (OpenStreetMap tiles usage policy; self-hosted tiles?).
- How uncertainty is shown (intervals, small multiples, hatching).
- Accessibility (keyboard, screen readers, colour-blind palettes).
- Bundle size and React integration.

## Decision

Not decided.

## Consequences

To be written with the decision.
