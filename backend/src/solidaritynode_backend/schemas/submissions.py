"""API models of submissions from a municipal installation to the hub (ADR 0014 Part A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "DownloadIn",
    "DownloadOut",
    "HubLinkOut",
    "PseudonymOut",
    "SendIn",
    "SubmissionEditIn",
    "SubmissionOut",
    "SubmissionSummaryOut",
]

Status = Literal[
    "draft",
    "sent",
    "received",
    "rejected_by_validation",
    "pending_review",
    "approved",
    "rejected",
    "published",
    "imported",
    "withdrawn",
]


class SubmissionSummaryOut(BaseModel):
    """A submission in the list."""

    id: uuid.UUID
    municipality_id: str
    kind: Literal["import", "manual"]
    status: Status
    file_name: str | None
    comment: str
    complete_list: bool
    created_at: datetime
    sent_at: datetime | None
    offline: bool
    last_error: str | None
    next_attempt_at: datetime | None
    hub_comment: str | None
    published_in: str | None
    imported_in: str | None
    withdraw_requested: bool
    summary: dict[str, int] | None
    errors: int | None
    created_by_name: str | None


class SubmissionEventOut(BaseModel):
    """A status transition: from, to, who (a local user or the hub) and when."""

    from_status: Status | None
    to_status: Status
    by_user: str | None
    by_hub: str | None
    at: datetime
    note: str


class SubmissionOut(SubmissionSummaryOut):
    """A submission with its local validation report, changeset preview and history."""

    base_package_version: str
    is_correction: bool
    report: dict[str, Any]
    items: list[dict[str, Any]]
    attempts: int
    hub_changeset_id: int | None
    hub_decided_at: datetime | None
    hub_conflicts: list[dict[str, Any]]
    submitted_by: str | None = Field(description="Pseudonymous id sent to the hub")
    events: list[SubmissionEventOut]


class ServiceInputs(BaseModel):
    """Capacity inputs of one service."""

    service_id: str
    places: float | None = None
    staff: float | None = None
    throughput: float | None = None
    throughput_unit: str | None = None


class SubmissionEditIn(BaseModel):
    """The edit form: add, change or close one facility of the active data."""

    municipality_id: str
    facility_id: str | None = None
    close: bool = False
    comment: str = ""
    values: dict[str, str | float | None] = Field(default_factory=dict)
    services: list[ServiceInputs] = Field(default_factory=list)


class SendIn(BaseModel):
    """Sending a draft; a complete list repeats the number of closures."""

    confirm_close: int | None = None


class PseudonymOut(BaseModel):
    """Which user a pseudonymous id stands for (administrators only)."""

    pseudonym: str
    username: str
    role: str


class DownloadOut(BaseModel):
    """A package download requested from the hub."""

    id: uuid.UUID
    version: str
    status: Literal["queued", "done", "failed"]
    staging_id: str | None
    error: str | None
    requested_at: datetime
    requested_by: str | None


class DownloadIn(BaseModel):
    """The package version to download."""

    version: str


class HubLinkOut(BaseModel):
    """The connection to the hub as recorded by the last sync (never the token)."""

    configured: bool
    hub_url: str
    token_present: bool
    sync_enabled: bool
    sync_seconds: float
    installation_id: str | None
    installation_name: str | None
    study_area_id: str | None
    last_sync_at: datetime | None
    last_contact_at: datetime | None
    last_error: str | None
    packages: list[dict[str, Any]]
    active_version: str | None
    new_versions: list[dict[str, Any]]
    downloads: list[DownloadOut]
