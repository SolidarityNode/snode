# Facility import

For the people who prepare facility files for the hub (hub staff and municipalities). The
processing behind it is [DP-004](DP-004-facility-imports.md); the screens are described in the
user guide, [Hub](../user-guide/hub.md).

**Facilities are organisations, not people.** Never enter the names of staff or responsible
persons, personal phone numbers or personal e-mails. Columns that look like personal data are
**dropped** on import and listed in the validation report; a mobile number in `public_phone` or
an e-mail of the form `first.last@…` in `public_email` is cleared and listed too. Give the
facility's public switchboard number and generic e-mail (for example `info@…`) instead.

## The template

Download it on the hub's **Facilities** screen: **XLSX** (with an `instructions` sheet in Greek
and English and one example row), **CSV** (header only) or **GeoPackage** (an empty point table
`facilities` in the hub CRS; the point gives the location, so `x`, `y`, `lon`, `lat` are not
needed). **One row per facility and service**: a facility with two services has two rows, with
the same facility columns.

| Column | Required | Meaning |
| --- | --- | --- |
| `facility_id` | no | Hub id of an existing facility (HF-…), to update it. Leave empty for a new facility. |
| `external_id` | no | Your own or an official registry code of the facility (optional); used to match rows to facilities on later imports. |
| `name` | yes | Name of the facility (an organisation, never a person). |
| `municipality` | yes | Municipality code, for example M-A. One municipality per file. |
| `x` | no | Easting in the hub CRS (metres), with y. Or give lon and lat. |
| `y` | no | Northing in the hub CRS (metres), with x. |
| `lon` | no | Longitude (WGS 84, degrees), with lat, if x and y are empty. |
| `lat` | no | Latitude (WGS 84, degrees), with lon. |
| `address` | no | Street address, stored as text only (it is not geocoded: coordinates are required). |
| `facility_type` | yes | Kind of facility, for example community_centre. |
| `service_id` | yes | One service the facility offers (from the services list). One row per facility and service: repeat the facility columns on each row. |
| `places` | no | Places for this service (a number, dot as decimal separator). |
| `staff` | no | Staff for this service, in persons (a number). |
| `throughput` | no | Throughput for this service, in the service's unit per reference period (a number). |
| `throughput_unit` | no | Unit of the throughput; must be the service's unit (for example appointment, hour). Required when throughput is given. |
| `operating_hours` | no | Opening hours as text, for example Mon-Fri 08:00-16:00. |
| `status` | no | open (default) or closed. closed closes an existing facility. |
| `quality` | yes | Data quality: open_data, estimated or verified_by_municipality. |
| `public_phone` | no | Public switchboard number of the facility. Never a personal or mobile number. |
| `public_email` | no | Generic e-mail of the facility (for example info@…). Never a person's e-mail. |
| `source` | no | Where the data comes from (register, survey, open data portal). |
| `notes` | no | Free notes about the facility (no personal data). |

Numbers use a **dot** as decimal separator. A CSV must be UTF-8 with commas; a file saved by a
Greek-locale spreadsheet with semicolons is refused with a message (save it as `.xlsx`
instead). Limits: 5 MB and 5,000 rows per file (`SOLIDARITYNODE_HUB_MAX_FACILITY_FILE_MB`,
`SOLIDARITYNODE_HUB_MAX_FACILITY_ROWS`). No geocoding service is called: rows without
coordinates are errors, whatever their address.

## What the hub checks

| Finding | Severity |
| --- | --- |
| Required field empty, unknown service, number not readable (or with a comma), negative value | error |
| Throughput unit not the unit of the service (for example `visit` for an appointment service) | error |
| Point outside the municipality, or in no spatial unit of it | error |
| `facility_id` that does not exist or belongs to another municipality | error |
| Rows of one facility that disagree | error |
| Column or value that looks like personal data (dropped) | warning |
| Column not in the template (ignored) | warning |
| Likely duplicate: same name in the municipality, or closer than 25 m (`SOLIDARITYNODE_HUB_DUPLICATE_DISTANCE_M`) | warning |
| Row matched to an existing facility by `external_id` | information |

A file with errors cannot be approved: fix it and upload it again. Warnings do not block.

## Matching and closing

1. A row with `facility_id` updates that facility.
2. Otherwise a row whose `external_id` belongs to a facility of the municipality updates it.
3. Otherwise the row is a **new** facility; the hub gives it a permanent id (`HF-000001`, …)
   when the changeset is approved. Ids are never reused.

Facilities **missing** from a file are **kept**. To close them, tick "this file is the complete
list of facilities of the municipality": the preview lists the closures and the approval asks
for their number. A facility is closed with an end date (`valid_to`), never deleted. To close
one facility, set its `status` to `closed` or use the edit form.

## Extending or correcting facilities

Download the current facilities of the municipality (**Facilities** screen, "Current
facilities in the template"), edit the file and import it again: rows keep their `facility_id`,
so only the changed fields appear in the preview. Tick "corrections" when the changes only fix
errors; the next package then gets a patch version (for example 1.1.1) instead of a minor one.

Exports (templates, reports, facility lists) escape spreadsheet formulas: a text starting with
`=`, `+`, `-` or `@` is written with a leading apostrophe, so it is never run as a formula.
