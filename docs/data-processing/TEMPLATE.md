# DP-NNN: <short title>

| Field | Value |
| --- | --- |
| Status | draft / done / superseded by DP-NNN |
| Author | |
| Date | YYYY-MM-DD |
| Municipality / study area | |
| Used in | data package id and version; paper and section |
| QGIS version | for example 3.40.x (plus plugins and versions) |
| Reproducible file | `data-processing/qgis/models/...model3` or `.../scripts/...py`, or "manual only" |

## Purpose
What this dataset is for, in one or two sentences (for example "road network for walking and car travel times, Paper 1 §5").

## Sources
| Source | Version / download date | Licence | File in `data/local/` |
| --- | --- | --- | --- |
| | | | |

## Coordinate reference system
Input CRS, output CRS (for example EPSG:2100, Greek Grid), reason for reprojection.

## Steps
Number every step. For QGIS tools paste the call from Processing → History.

1. **<what and why>**
   ```python
   processing.run("native:...", {...})
   ```
2. **Manual edit:** <what was changed, which features, why>

## Output
| File in `data/local/` | Layers / tables | Feature count | Key fields |
| --- | --- | --- | --- |
| | | | |

## Checks
- [ ] CRS is the expected one
- [ ] Feature counts before and after each filtering step (list them)
- [ ] Geometry validity (Vector → Geometry Tools → Check Validity)
- [ ] Visual check against a basemap (screenshot below if useful)
- [ ] Spot checks: <for example travel time between two known points>

## Assumptions and limitations
Choices made that could affect results (for example "missing speed limits set to 50 km/h", "population assigned by area-weighting").

## Open issues
Anything to fix later, or questions for the method (link `OQ-n` if relevant).
