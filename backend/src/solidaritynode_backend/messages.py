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

__all__ = ["BACKEND_MESSAGES", "all_messages", "messages_json", "msg"]

BACKEND_MESSAGES: Final[Mapping[str, str]] = MappingProxyType(
    {
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
