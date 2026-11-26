# DP-004: Facility imports and edits in the hub

| Field | Value |
| --- | --- |
| Status | done (v0.2) |
| Author | SolidarityNode contributors |
| Date | 2026-11-26 |
| Municipality / study area | any municipality whose base step is done (DP-003) |
| Used in | the `facilities` layer and `tables/facility_services.csv` of hub packages |
| QGIS version | not used; files may be prepared in QGIS or a spreadsheet program |
| Reproducible file | `backend/src/solidaritynode_backend/services/hub/facilities.py` |

## Purpose
Add, correct and close the facilities of a municipality from a spreadsheet or GeoPackage, or by
hand, with a validation report, a preview of the changes and an approval, keeping the history
of every facility. The file format is described for its users in
[Facility import](facility-import.md).

## Sources
Files sent by municipalities or prepared by the hub (CSV, XLSX or GeoPackage in the import
template). Each approved changeset records the file name, its SHA-256, the source, the licence
and the attribution stated at upload, author, date and comment. The file is kept in the hub
storage (`imports/`).

## Coordinate reference system
`x`/`y` in the hub CRS, or `lon`/`lat` in WGS 84 (EPSG:4326), or the CRS of a GeoPackage point
table; everything is transformed to the hub CRS with PostGIS. No geocoding: an address is text
only.

## Steps
1. **Parse** the file; drop columns that look like personal data (and list them), ignore other
   unknown columns (and list them); clear public phone numbers that are Greek mobile numbers and
   e-mails of the form `first.last@` (and list them).
2. **Validate** every row (required fields, known service, numbers with a dot, no negative
   values, throughput unit equal to the service unit, quality and status values) and every
   facility (consistent rows, coordinates inside the municipality, a spatial unit containing
   the point; nearest network node).
3. **Match**: `facility_id`, then `external_id` among the municipality's facilities; otherwise
   new. Likely duplicates (same normalised name in the municipality, or within
   `SOLIDARITYNODE_HUB_DUPLICATE_DISTANCE_M`) are warnings.
4. **Preview**: added, updated (field-level diff, services as `services.<id>.<input>`),
   closed. Facilities absent from the file are closed **only** when the file is declared the
   complete list of the municipality.
5. **Approve** (administrator): new ids `HF-000001`… from a sequence that never goes back;
   closures set `valid_to`; a processing record (kind `facility_changeset`) is written; the
   municipality moves from `base_ready` to `facilities_in_progress`.

## Output
`hub_features` rows of layer `facilities` (`processing_note` `DP-004`), `hub_changesets` and
`hub_changeset_items` (the history).

## Checks
- [x] Tests: valid file, file with errors, personal-data columns, re-import with one change,
      partial import, complete list, formula escaping in exports (`backend/tests/hub/test_facilities.py`)
- [x] Approval refused when the report has errors, when a complete list is not confirmed with
      the number of closures, or when a facility changed after the preview

## Assumptions and limitations
- The personal-data detection is a list of header patterns and two value patterns; it cannot
  recognise every case. The template and the screen say that facilities are organisations and
  no personal data may be entered.
- Each row lists all services of a facility; a service missing from an update is removed.

## Open issues
The flow by which a municipality submits corrections (`source` "submitted by municipality X")
is a separate issue (ADR 0014).
