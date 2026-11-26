"""Backend messages for people: English templates with stable codes (see core ``messages``).

Every error and status text the API returns to the UI is rendered from here. ``make schemas``
exports these with core's templates to ``docs/schemas/messages.json``; the frontend translates
by code. Package validation errors (``services/packages.py``) are the exception: technical
diagnostics for administrators that quote file, table and column names, shown in English under
a translated heading (docs/i18n/glossary.md).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from solidaritynode_core.model.messages import CORE_MESSAGES, render

__all__ = ["BACKEND_MESSAGES", "HUB_MESSAGES", "all_messages", "messages_json", "msg"]

HUB_MESSAGES: Final[Mapping[str, str]] = MappingProxyType(
    {
        # Hub: general errors
        "hub.error.municipality_unknown": (
            "municipality {municipality} is not in the registered boundaries"
        ),
        "hub.error.transition_not_allowed": (
            "{municipality}: the status cannot change from {current} to {target}"
        ),
        "hub.error.source_not_found": "source {id} not found",
        "hub.error.changeset_not_found": "changeset {id} not found",
        "hub.error.changeset_decided": "changeset {id} was already {state}",
        "hub.error.facility_not_found": "facility {id} not found",
        "hub.error.study_area_not_found": "study area {id} not found",
        "hub.error.study_area_exists": "study area {id} already exists",
        "hub.error.package_not_found": "package {id} {version} not found",
        "hub.error.job_not_found": "job not found",
        "hub.error.not_onboarded": (
            "municipality {municipality} has no base data yet: run the base step first"
        ),
        # Hub: raw sources
        "hub.source.field_required": "{field} is required",
        "hub.source.unknown_layer_type": "unknown layer type {layer_type} (allowed: {allowed})",
        "hub.source.bad_note": "processing note {note} must look like DP-001",
        "hub.source.bad_quality": "unknown quality {quality}",
        "hub.source.not_gpkg": "{file} is not a GeoPackage: {detail}",
        "hub.source.missing_table": "{file} has no {kinds} table with the columns {columns}",
        "hub.source.not_utf8": "{file} is not UTF-8 text",
        "hub.source.missing_columns": "{file}: the header row lacks {columns}",
        "hub.source.too_large": "the file is larger than {limit} MB",
        "hub.source.empty": "the file is empty",
        "hub.source.version_conflict": (
            "source {name} version {version} is already registered with different content; "
            "register it as a new version"
        ),
        # Hub: base step of onboarding (DP-003)
        "hub.base.missing_sources": "register these source types first: {layers}",
        "hub.base.already_running": "a base step for {municipality} is already queued or running",
        "hub.base.crs_unknown": "source {source} declares the CRS {crs}, which is not an EPSG code",
        "hub.base.reprojected": "source {source} was reprojected from {source_crs} to {crs}",
        "hub.base.municipality_without_code": ("a boundary without municipality_code was skipped"),
        "hub.base.invalid_geometry": "{layer} {id}: invalid geometry",
        "hub.base.duplicate_code": "{layer}: the code {id} appears {count} times",
        "hub.base.no_units": "municipality {municipality} has no spatial units in the source",
        "hub.base.node_without_code": "a network node without node_code was found",
        "hub.base.edges_outside": "{count} edge(s) with an end outside the area were left out",
        "hub.base.edge_values": "edge {id}: length or travel times missing or negative",
        "hub.base.centroid_rule": (
            "{count} spatial unit(s) were linked to the network node nearest to a point inside "
            "them (DP-003)"
        ),
        "hub.base.unit_without_node": "spatial unit {id} has no network node",
        "hub.base.components": "the network of the area has {count} connected part(s)",
        "hub.base.unit_disconnected": (
            "spatial unit {id}: its node {node} is not connected to the main network"
        ),
        "hub.base.population_unknown_group": "population line {line}: unknown group {group}",
        "hub.base.population_not_count": ("population line {line}: {value} is not a whole number"),
        "hub.base.population_duplicate": "population: unit {unit} has group {group} twice",
        "hub.base.population_missing": "population: unit {unit} has no value for {groups}",
        "hub.base.population_total": "population of {municipality}: {total} (all groups summed)",
        "hub.base.population_mismatch": (
            "population of {municipality}: {stored} stored but {source} in the source"
        ),
        "hub.base.source_unreadable": "a source could not be read: {detail}",
        "hub.base.cancelled": "cancelled; nothing was stored",
        "hub.base.crashed": "the base step failed and nothing was stored: {detail}",
        "hub.base.stopped": "stopped by {errors} error(s); nothing was stored",
        "hub.base.summary": (
            "{municipality}: {added} feature(s) added, {changed} changed, {closed} closed"
        ),
        "hub.base.status_note": "base step, processing record {record}",
        # Hub: facility import and changesets (DP-004)
        "hub.import.unsupported_type": "{file}: unsupported file type (use .csv, .xlsx or .gpkg)",
        "hub.import.not_utf8": "{file} is not UTF-8 text; save it as CSV UTF-8 or as .xlsx",
        "hub.import.semicolon": (
            "{file} uses ';' as delimiter (as a Greek-locale spreadsheet does); save it as .xlsx, "
            "or as CSV with commas and a dot as decimal separator"
        ),
        "hub.import.unreadable": "{file} cannot be read: {detail}",
        "hub.import.too_many_rows": "the file has more than {limit} rows; split it",
        "hub.import.no_rows": "{file} has no data rows",
        "hub.import.no_header": "the file has no header row",
        "hub.import.personal_column": (
            "column {column} looks like personal data and was dropped (facilities are "
            "organisations, not people)"
        ),
        "hub.import.unknown_column": "column {column} is not in the template and was ignored",
        "hub.import.personal_value": (
            "row {row}, {column}: looks like personal contact data and was dropped; give the "
            "facility's public switchboard or generic e-mail"
        ),
        "hub.import.required": "row {row}: {column} is required",
        "hub.import.other_municipality": (
            "row {row}: municipality {value} is not the municipality of this import "
            "({municipality})"
        ),
        "hub.import.unknown_service": "row {row}: unknown service {service}",
        "hub.import.wrong_unit": (
            "row {row}: throughput unit {unit} does not match the unit of {service} ({expected})"
        ),
        "hub.import.comma_decimal": (
            "row {row}, {column}: {value} uses a comma as decimal separator; use a dot"
        ),
        "hub.import.not_number": "row {row}, {column}: {value} is not a number",
        "hub.import.negative": "row {row}, {column}: {value} must not be negative",
        "hub.import.bad_quality": (
            "row {row}: unknown quality {value} (open_data, estimated or verified_by_municipality)"
        ),
        "hub.import.bad_status": "row {row}: status must be open or closed, not {value}",
        "hub.import.inconsistent": (
            "row {row}: {column} differs from an earlier row of the same facility"
        ),
        "hub.import.duplicate_service": (
            "row {row}: service {service} appears twice for one facility"
        ),
        "hub.import.no_coordinates": (
            "row {row}: no coordinates; give x and y or lon and lat (addresses are not geocoded)"
        ),
        "hub.import.outside_municipality": (
            "row {row}: the point is outside municipality {municipality}"
        ),
        "hub.import.no_unit": "row {row}: no spatial unit of {municipality} contains the point",
        "hub.import.unknown_id": (
            "row {row}: facility {id} does not exist; leave facility_id empty for a new facility"
        ),
        "hub.import.id_other_municipality": (
            "row {row}: facility {id} belongs to another municipality, not {municipality}"
        ),
        "hub.import.matched_external": (
            "row {row}: matched facility {id} by external id {external_id}"
        ),
        "hub.import.matched_twice": "row {row}: facility {id} appears twice in the file",
        "hub.import.new_closed": "row {row}: a new facility cannot be closed",
        "hub.import.duplicate_name": (
            "row {row}: same name as {other} in this municipality (likely duplicate)"
        ),
        "hub.import.duplicate_near": "row {row}: {distance} m from {other} (likely duplicate)",
        "hub.import.complete_list": (
            "complete list of {municipality}: {count} open facility(ies) not in the file will be "
            "closed"
        ),
        "hub.import.has_errors": (
            "changeset {id} has errors in its validation report; fix the file and upload it again"
        ),
        "hub.import.confirm_close": (
            "confirm the complete list of {municipality}: type the number of facilities that will "
            "be closed ({count})"
        ),
        "hub.import.stale": (
            "facility {id} changed after this preview was made; upload the file again"
        ),
        "hub.import.summary": (
            "changeset {changeset} ({municipality}): {added} added, {updated} updated, "
            "{closed} closed"
        ),
        "hub.import.status_note": "first approved facility changeset {changeset}",
        # Hub: study areas, publishing and propagation (DP-006)
        "hub.study_area.bad_id": (
            "study area id {id} must be 2-63 lower-case letters, digits or hyphens"
        ),
        "hub.study_area.bad_rule": "unknown buffer rule {rule}",
        "hub.publish.building": "version {version} of {id} is being built; wait for it to finish",
        "hub.publish.no_changes": (
            "nothing changed for {id} since version {version}; there is nothing to publish"
        ),
        "hub.publish.failed": "publishing failed; nothing was published: {detail}",
        "hub.publish.invalid": "the assembled package does not pass the import checks: {detail}",
        "hub.publish.summary": "published {id} {version}",
        "hub.publish.status_note": "published in {id} {version}",
        "hub.publish.initial": "First version of study area {id}.",
        # Submissions from municipal installations (ADR 0014 Part A)
        "hub.submission.not_core": (
            "municipality {municipality} is not a core municipality of this installation's "
            "study area; only core municipalities can be corrected from here"
        ),
        "hub.submission.source": (
            "submitted by municipality {municipality} (installation {installation}, user {user}, "
            "{role})"
        ),
        "hub.submission.attribution": "Municipality {municipality}",
        "hub.submission.other_installation": (
            "submission {id} was already received from another installation"
        ),
        "hub.submission.validation_failed": (
            "rejected by the hub's validation; see the validation report"
        ),
        "hub.submission.withdrawn_note": "withdrawn by the municipality",
        "hub.submission.not_found": "submission {id} not found",
        "hub.submission.review_started": (
            "submission {id} can no longer be withdrawn: the hub has started reviewing it"
        ),
        "hub.submission.unresolved_conflicts": (
            "changeset {id} has conflicts: choose for each one whether to apply the "
            "municipality's change or keep the hub's value"
        ),
        "hub.submission.bad_file": "this is not a valid submission file: {detail}",
        "hub.submission.bad_signature": (
            "the submission file's signature does not match a registered installation"
        ),
        "hub.submission.study_area_missing": (
            "study area {id} of this installation is not registered in the hub yet"
        ),
        "hub.installation.not_found": "installation {id} not found",
        "hub.installation.exists": "an installation named {name} already exists",
        "hub.installation.unauthorised": "missing, unknown or revoked installation token",
    }
)
"""Hub message templates by code (ADR 0012); part of :data:`BACKEND_MESSAGES`."""

BACKEND_MESSAGES: Final[Mapping[str, str]] = MappingProxyType(
    {
        **HUB_MESSAGES,
        # Sign-in and roles (ADR 0015)
        "error.login_required": "login required",
        "error.requires_role": "requires role {roles}",
        "error.requires_editor": "requires role analyst or admin",
        "error.wrong_credentials": "wrong username or password",
        "error.too_many_attempts": "too many failed sign-in attempts; try again later",
        "error.password_short": "password must have at least {length} characters",
        "error.password_common": (
            "this password is on the list of commonly used passwords; choose another one"
        ),
        "error.user_exists": "user {username} already exists",
        "error.unknown_role": "unknown role {role}",
        "error.user_not_found": "user not found",
        "error.self_demote": "you cannot demote or disable yourself",
        "error.last_admin": "the last active administrator cannot be disabled or demoted",
        # Data
        "error.no_data": "no data package imported yet",
        "error.data_version_not_found": "data version not found",
        "error.unknown_layer": "unknown layer {layer}",
        "error.empty_upload": "empty upload",
        "error.upload_too_large": "package larger than 64 MB",
        # Scenarios
        "error.scenario_not_found": "scenario not found",
        "error.version_not_found": "version not found",
        "error.scenario_version_not_found": "scenario version not found",
        "error.scenario_mismatch": "the scenario does not match the data",
        "error.scenario_mismatch_in": "the scenario does not match data {version}",
        "error.only_owner_edit": "only the owner or an admin can edit",
        "error.only_owner_delete": "only the owner or an admin can delete",
        "error.only_owner_run": "only the owner or an admin can run it",
        "error.hard_delete_has_runs": (
            "the scenario has {runs} run(s); it can only be deleted softly"
        ),
        # Runs
        "error.run_not_found": "run not found",
        "error.only_starter_cancel": "only who started the run or an admin",
        "error.no_results": "the run has no results (not succeeded)",
        "error.no_baseline": "no succeeded baseline run on data {version} yet",
        "error.compare_data_versions": (
            "the runs use different data versions ({a} and {b}); compare runs on the same "
            "data version, or two runs of the same scenario"
        ),
        "error.samples_missing": "samples file of run {run} is missing: {file}",
        "error.samples_mismatch": (
            "samples file of run {run} does not match its recorded SHA-256: it was "
            "damaged or changed after the run"
        ),
        "error.samples_other_run": "samples file {file} belongs to run {other}, not {run}",
        "run.reuse_refused": (
            "An earlier run with the same inputs was not reused because its results file "
            "failed the integrity check ({details}). This run computes the results again."
        ),
        "run.reuse_refused_item": "run {run}: {detail}",
        "run.cancelled_running": "Cancelled by a user while running.",
        "run.cancelled_queued": "Cancelled before it started.",
        "run.interrupted": (
            "Interrupted: the worker ({worker}) stopped while this run was running ({when}). "
            "No results were stored. Start the run again."
        ),
        "run.failed_exception": "{type}: {detail}",
        "run.no_heartbeat": "no heartbeat since {time}",
        "run.never_started": "never started",
        "run.timed_out": (
            "Stopped: the job ran longer than the maximum runtime of {limit:g} s set for "
            "'{kind}' jobs (SOLIDARITYNODE_JOB_MAX_RUNTIME_SECONDS). No results were stored."
        ),
        "run.queued_other_code": (
            "This run was queued for code {queued}, but the platform now runs code {current} "
            "(it was upgraded or rebuilt before the run started). The run cannot be reproduced "
            "as recorded. Start the run again."
        ),
        "run.queued_other_model": (
            "This run was queued for model {model} {queued}, but the platform now has "
            "{current}. Start the run again."
        ),
    }
)
"""Backend message templates by code."""


def msg(code: str, /, **params: object) -> str:
    """Return backend message ``code`` rendered with ``params``."""
    return render(BACKEND_MESSAGES, code, **params)


def all_messages() -> dict[str, str]:
    """Return core and backend templates together (exported by ``make schemas``)."""
    overlap = set(CORE_MESSAGES) & set(BACKEND_MESSAGES)
    if overlap:
        raise ValueError(f"message codes defined twice: {sorted(overlap)}")
    return dict(sorted({**CORE_MESSAGES, **BACKEND_MESSAGES}.items()))


def messages_json() -> str:
    """Return :func:`all_messages` as the JSON text of ``docs/schemas/messages.json``."""
    return json.dumps(all_messages(), indent=2, ensure_ascii=False) + "\n"
