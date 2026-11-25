# 0007. Frontend map library

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
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

**Accepted for v0.1, to be revisited: option 2, Leaflet** (BSD-2-Clause), used directly with a
small React wrapper (`frontend/src/map/MapView.tsx`). `react-leaflet` is **not** used: its
licence (Hippocratic-2.1) is not compatible with AGPL-3.0.

- Basemap configurable with `SOLIDARITYNODE_BASEMAP`: `osm` (OpenStreetMap standard tiles with
  the required attribution, light interactive use within the OSMF tile usage policy) or `blank`
  (no tiles, for offline use and tests).
- The backend reprojects layers to EPSG:4326 with PostGIS; the frontend only displays.
- Styling: core units solid, buffer units grey and dashed; quality shown with SVG patterns
  (hatching = estimated, dots = open data); edge-effect units with an orange outline; results in
  viridis (sequential) and PuOr (diverging), both readable with common colour-vision deficiencies.
- **Uncertainty on maps** (AGENTS.md invariant 6). Results maps and per-unit tables show the
  **median** and its interval (ADR 0017); the mean is stored and exported, not mapped. **Every
  displayed value names its statistic**: column headings "Median (90 % interval)", tooltips
  "Unit A3, median (90 % interval): 0.42 (0.31–0.55)", legend titles "…, median (min)" and the
  note under each map. The interval name comes from the run's quantile levels ("90 % interval"
  for 0.05/0.95, "10–95 % quantile interval" for asymmetric levels, "interval (levels not
  recorded)" for older runs); comparison headings name each run's interval. Differences are
  "Difference of medians A − B". An **Uncertainty** toggle
  (off by default) adds a second map of the interval width (`high − low`) in its own palette
  (Blues), next to the value map; on comparison screens it switches maps A and B to the width.
  Hatching and dots are **never** used for uncertainty: they mean data quality. Tooltips and
  tables always show the interval with the median, for example `0.42 (0.31–0.55)`; deterministic
  values say so. Probability outputs (indicator unit `probability`) use a **fixed 0–1 scale**
  (classes of 0.2) labelled as a probability, never a range stretched to the data.
- **Comparison screens** (baseline vs scenario, and the same scenario across data versions) build
  **one** colour scale from the values of both runs and show **one** legend for maps A and B, so
  equal values have equal colours (test: `frontend/src/pages/ComparePage.test.tsx`). The
  difference map keeps its own diverging scale and legend.
- **Data-quality layer.** On results and comparison maps the quality patterns are a toggleable
  layer, **off by default**, so they do not hide the value colours; the results table always marks
  units of `estimated` or `open_data` quality in words, and a note says how many there are. The
  study-area screen always shows the patterns.
- **Referrer.** Map tiles must be requested with a valid Referer (OSMF tile usage policy). nginx
  sends `Referrer-Policy: strict-origin-when-cross-origin` on every response and the Leaflet tile
  layer sets the same policy on its tile images; never use `no-referrer` or `same-origin`
  (checked by the end-to-end test).
- Accessibility: the map container is keyboard-focusable (arrows pan, +/- zoom), every map has a
  text list of its features and a legend in words.

**Why:** the demo and first municipalities have few polygons, so raster-first Leaflet is enough;
it is small, well known and simple to wrap without a React binding.

## Consequences

- Layer size triggers: above about **1,000 features** in one map, switch Leaflet to its canvas
  renderer (`preferCanvas`) instead of SVG. Above about **2,000 polygons**, or for **national
  views in the hub**, revisit with MapLibre GL JS (BSD-3-Clause) and vector tiles. Note that the
  canvas renderer cannot use the SVG quality patterns as they are; that change needs its own
  quality marking.
- **OpenStreetMap's public tile servers are for development and demos only.** The OSMF Tile
  Usage Policy (https://operations.osmfoundation.org/policies/tiles/) gives no SLA and allows
  access to be withdrawn at any time without notice. Production installations need their own
  tiles or a tile provider whose terms cover their traffic.
- Basemap options for later (none implemented now; the `osm | blank` setting stays for v0.1):
  - **Preferred for production: self-hosted PMTiles (Protomaps).** The hub produces one basemap
    extract per data package (same extent as the study area), served as a static file by the
    installation itself: no tile server, no third-party traffic, works offline.
  - **For demos and pilots: OpenFreeMap**, a free hosted vector-tile service, when
    self-hosting is not yet set up.
  - Both are vector basemaps. When vector basemaps are adopted, **MapLibre GL JS**
    (BSD-3-Clause) is the candidate replacement for Leaflet; record that change in a new ADR.
- Leaflet stays for v0.1.
