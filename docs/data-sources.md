# Data sources

Every third-party dataset used by SolidarityNode is listed here with its licence and required attribution (AGENTS.md "Data and privacy rules"). Real data is **never** committed to the repository; only synthetic data lives under `data/synthetic/` and `core/tests/fixtures/`. Choice of sources: ADR 0009.

| Source | Provider | Licence | Required attribution | Use in SolidarityNode | Added |
| --- | --- | --- | --- | --- | --- |
| *(none yet)* | | | | | |

## Real open data stays local

Open datasets planned for the first application (OpenStreetMap, ELSTAT population, a DEM,
GTFS public transport feeds) will be **downloaded to `data/local/` by scripts in later
tickets**. `data/local/` is git-ignored: nothing in it is ever committed. Each downloaded source
gets a row in the table above and each processed dataset a `DP-NNN` note in
[`docs/data-processing/`](data-processing/README.md). No real data has been downloaded yet.

The synthetic demo dataset (`data/synthetic/demo/`, DP-001) uses no third-party source.

How to add a source:

1. Check that the licence allows our use (and redistribution of derived results, if any).
2. Add a row with the exact attribution text and a link to the licence.
3. Show the attribution wherever the data is displayed (for example map attributions in the frontend).
4. Note any share-alike obligations for derived data (for example ODbL for OpenStreetMap).
