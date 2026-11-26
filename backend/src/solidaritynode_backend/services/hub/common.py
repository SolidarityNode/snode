"""Shared hub definitions: layers, qualities, processing records and onboarding status.

Onboarding status per municipality (Spec 00 §3 Onboarding):
``not_started → base_ready → facilities_in_progress → in_review → published``. Every transition
is stored with who and when (``hub_onboarding_events``).

Every automated processing step writes a **processing record** (``hub_processing_records``):
inputs with versions and checksums, parameters, outputs, checks and the ``DP-NNN`` note it
implements (docs/data-processing/README.md).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.messages import msg

__all__ = [
    "BASE_NOTE",
    "COVERAGE_LAYERS",
    "FACILITY_NOTE",
    "PUBLISH_NOTE",
    "QUALITY",
    "QUALITY_RANK",
    "STATUSES",
    "VERIFIED",
    "Check",
    "HubError",
    "add_record",
    "check",
    "ensure_municipality",
    "finish_record",
    "jsonb",
    "set_status",
    "worst_quality",
]

VERIFIED = "verified_by_municipality"
QUALITY = ("open_data", "estimated", VERIFIED)
QUALITY_RANK = {"missing": 0, "estimated": 1, "open_data": 2, VERIFIED: 3}
"""Order used for a layer's coverage: the worst quality of its features."""

COVERAGE_LAYERS = (
    "boundaries",
    "spatial_units",
    "population",
    "network",
    "facilities",
    "transit",
    "susceptibility",
)
"""Layers of the coverage matrix (and of every package manifest's ``coverage``)."""

STATUSES = ("not_started", "base_ready", "facilities_in_progress", "in_review", "published")
BASE_NOTE = "DP-003"
"""Processing note of the automated base step (docs/data-processing/)."""
FACILITY_NOTE = "DP-004"
"""Processing note of facility imports and edits."""
PUBLISH_NOTE = "DP-006"
"""Processing note of package assembly."""

Severity = Literal["error", "warning", "info"]
Check = dict[str, Any]
"""``{"code", "severity", "message", "params"}``; ``message`` is rendered from ``code``."""

# Allowed manual transitions; the base step, facility approvals and publishing move the status
# automatically (see the functions that call :func:`set_status`).
MANUAL_TRANSITIONS = {
    ("facilities_in_progress", "in_review"),
    ("base_ready", "in_review"),
    ("in_review", "facilities_in_progress"),
}


class HubError(ValueError):
    """A hub request cannot be done; the message is a catalogue text (translated in the UI)."""

    def __init__(self, code: str, /, status: int = 422, **params: object) -> None:
        """Render message ``code`` with ``params``; ``status`` is the HTTP status to answer."""
        super().__init__(msg(code, **params))
        self.code = code
        self.status = status


def check(code: str, severity: Severity, /, **params: object) -> Check:
    """Return a check or report entry with its message rendered from the catalogue."""
    return {"code": code, "severity": severity, "message": msg(code, **params), "params": params}


def jsonb(value: object) -> str:
    """Serialise ``value`` for a ``CAST(:x AS jsonb)`` parameter."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def worst_quality(qualities: Iterable[str]) -> str:
    """Return the worst of ``qualities`` (``missing`` if there are none)."""
    values = list(qualities)
    return min(values, key=lambda q: QUALITY_RANK[q]) if values else "missing"


def add_record(
    db: Session,
    kind: str,
    *,
    note: str,
    municipality_id: str | None = None,
    study_area_id: str | None = None,
    inputs: Sequence[Mapping[str, Any]] = (),
    parameters: Mapping[str, Any] | None = None,
    user_id: int | None = None,
) -> int:
    """Create a running processing record and return its id."""
    return int(
        db.execute(
            text(
                "INSERT INTO hub_processing_records (kind, municipality_id, study_area_id, status, "
                "processing_note, inputs, parameters, created_by) VALUES (:k, :m, :s, 'running', "
                ":n, CAST(:i AS jsonb), CAST(:p AS jsonb), :u) RETURNING id"
            ),
            {
                "k": kind,
                "m": municipality_id,
                "s": study_area_id,
                "n": note,
                "i": jsonb(list(inputs)),
                "p": jsonb(dict(parameters or {})),
                "u": user_id,
            },
        ).scalar_one()
    )


def finish_record(
    db: Session,
    record_id: int,
    *,
    status: Literal["succeeded", "failed"],
    outputs: Mapping[str, Any] | None = None,
    checks: Sequence[Check] = (),
    affected: Iterable[str] = (),
    changed: bool = False,
    summary: str = "",
    job_id: str | None = None,
) -> None:
    """Record the outcome of a processing step."""
    db.execute(
        text(
            "UPDATE hub_processing_records SET status = :st, outputs = CAST(:o AS jsonb), "
            "checks = CAST(:c AS jsonb), affected_municipalities = :a, changed = :ch, "
            "summary = :su, finished_at = now(), job_id = coalesce(CAST(:j AS uuid), job_id) "
            "WHERE id = :id"
        ),
        {
            "st": status,
            "o": jsonb(dict(outputs or {})),
            "c": jsonb(list(checks)),
            "a": sorted(set(affected)),
            "ch": changed,
            "su": summary,
            "j": job_id,
            "id": record_id,
        },
    )


def ensure_municipality(db: Session, municipality_id: str, name: str) -> str:
    """Create the onboarding row of a municipality if missing; return its status."""
    db.execute(
        text(
            "INSERT INTO hub_onboarding (municipality_id, name) VALUES (:m, :n) "
            "ON CONFLICT (municipality_id) DO NOTHING"
        ),
        {"m": municipality_id, "n": name},
    )
    return str(
        db.execute(
            text("SELECT status FROM hub_onboarding WHERE municipality_id = :m"),
            {"m": municipality_id},
        ).scalar_one()
    )


def set_status(
    db: Session,
    municipality_id: str,
    to_status: str,
    user_id: int | None,
    note: str = "",
    *,
    only_from: Iterable[str] | None = None,
) -> bool:
    """Move a municipality to ``to_status`` and record the transition.

    Args:
        db: Session (the caller commits).
        municipality_id: Municipality code.
        to_status: New status.
        user_id: Who caused the change (``None``: the system).
        note: Why, for the history (for example the processing record).
        only_from: If given, change only when the current status is one of these.

    Returns:
        Whether the status changed.
    """
    current = db.execute(
        text("SELECT status FROM hub_onboarding WHERE municipality_id = :m FOR UPDATE"),
        {"m": municipality_id},
    ).scalar_one_or_none()
    if current is None or current == to_status:
        return False
    if only_from is not None and current not in set(only_from):
        return False
    db.execute(
        text(
            "UPDATE hub_onboarding SET status = :s, updated_at = now() WHERE municipality_id = :m"
        ),
        {"s": to_status, "m": municipality_id},
    )
    db.execute(
        text(
            "INSERT INTO hub_onboarding_events (municipality_id, from_status, to_status, by_user, "
            "note) VALUES (:m, :f, :t, :u, :n)"
        ),
        {"m": municipality_id, "f": current, "t": to_status, "u": user_id, "n": note},
    )
    return True


def manual_transition(db: Session, municipality_id: str, to_status: str, user_id: int) -> None:
    """Apply a transition chosen by a person (for example "ready for review").

    Raises:
        HubError: If the municipality is unknown or the transition is not allowed.
    """
    current = db.execute(
        text("SELECT status FROM hub_onboarding WHERE municipality_id = :m"),
        {"m": municipality_id},
    ).scalar_one_or_none()
    if current is None:
        raise HubError("hub.error.municipality_unknown", status=404, municipality=municipality_id)
    if (current, to_status) not in MANUAL_TRANSITIONS:
        raise HubError(
            "hub.error.transition_not_allowed",
            status=409,
            municipality=municipality_id,
            current=current,
            target=to_status,
        )
    set_status(db, municipality_id, to_status, user_id)
