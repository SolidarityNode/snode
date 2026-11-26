"""API models of the hub (ADR 0012): sources, onboarding, facilities, coverage, publishing."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "ApproveIn",
    "ChangesetOut",
    "ChangesetSummaryOut",
    "CheckOut",
    "CoverageCellOut",
    "CoverageRowOut",
    "FacilityEditIn",
    "FacilityOut",
    "HistoryEntryOut",
    "JobOut",
    "OnboardingDetailOut",
    "OnboardingEventOut",
    "PackageOut",
    "PendingOut",
    "PublishIn",
    "PublishOut",
    "RecordOut",
    "RejectIn",
    "SourceOut",
    "StartedOut",
    "StatusIn",
    "StudyAreaIn",
    "StudyAreaOut",
]

Quality = Literal["open_data", "estimated", "verified_by_municipality"]
Coverage = Literal["missing", "open_data", "estimated", "verified_by_municipality"]
OnboardingStatus = Literal[
    "not_started", "base_ready", "facilities_in_progress", "in_review", "published"
]


class CheckOut(BaseModel):
    """One check of a processing record or one entry of a validation report.

    ``message`` is an English text from the message catalogue; the UI translates it by
    ``code``.
    """

    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    params: dict[str, Any] = Field(default_factory=dict)


class SourceOut(BaseModel):
    """A registered raw source (nothing is processed at registration)."""

    id: int
    name: str
    layer_type: str
    coverage: str
    version: str
    licence: str
    attribution: str
    processing_note: str
    quality: Quality
    synthetic: bool
    file_name: str
    sha256: str
    bytes: int
    details: dict[str, Any]
    registered_at: datetime
    created: bool = Field(
        default=True, description="False when the same name, version and content existed"
    )


class JobOut(BaseModel):
    """A background job of the hub (base step or package assembly)."""

    id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float
    error: str | None
    cancel_requested: bool


class RecordOut(BaseModel):
    """A processing record: inputs with versions and checksums, parameters, outputs, checks."""

    id: int
    kind: str
    municipality_id: str | None
    study_area_id: str | None
    status: Literal["running", "succeeded", "failed"]
    processing_note: str
    inputs: list[dict[str, Any]]
    parameters: dict[str, Any]
    outputs: dict[str, Any]
    checks: list[CheckOut]
    affected_municipalities: list[str]
    changed: bool
    summary: str
    created_at: datetime
    finished_at: datetime | None
    created_by_name: str | None = None
    job: JobOut | None = None


class OnboardingEventOut(BaseModel):
    """A status transition: from, to, who and when."""

    from_status: OnboardingStatus | None
    to_status: OnboardingStatus
    by: str | None
    at: datetime
    note: str


class CoverageCellOut(BaseModel):
    """Status of one layer of one municipality."""

    status: Coverage
    version: str
    updated_at: datetime | None


class CoverageRowOut(BaseModel):
    """One municipality of the coverage matrix (and of the onboarding list)."""

    municipality_id: str
    name: str
    status: OnboardingStatus
    onboarded: bool
    layers: dict[str, CoverageCellOut]


class OnboardingDetailOut(BaseModel):
    """One municipality: status, history, base-step reports, facilities and changesets."""

    municipality_id: str
    name: str
    status: OnboardingStatus
    layers: dict[str, CoverageCellOut]
    events: list[OnboardingEventOut]
    records: list[RecordOut]
    job: JobOut | None
    facilities_open: int
    facilities_closed: int


class StartedOut(BaseModel):
    """A queued job and its processing record."""

    record_id: int
    job_id: str


class StatusIn(BaseModel):
    """A status chosen by a person (for example ready for review)."""

    status: OnboardingStatus


class FacilityOut(BaseModel):
    """A curated facility (open or closed)."""

    facility_id: str
    municipality_id: str
    properties: dict[str, Any]
    quality: Quality
    valid_from: date
    valid_to: date | None
    x: float
    y: float


class ChangesetItemOut(BaseModel):
    """One change: a facility added, updated (with the changed fields) or closed."""

    item_no: int
    action: Literal["add", "update", "close"]
    facility_id: str | None
    label: str
    rows: list[int]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    fields: list[str]
    conflict: dict[str, Any] | None = Field(
        default=None,
        description="Municipal submissions: the facility changed in the hub since the "
        "municipality's package (fields, municipality's, hub's and proposed values)",
    )
    resolution: Literal["municipality", "hub"] | None = None


class ChangesetSummaryOut(BaseModel):
    """A changeset in a list."""

    id: int
    kind: Literal["import", "manual", "submission"]
    municipality_id: str
    status: Literal["pending", "approved", "rejected", "withdrawn"]
    source: str
    comment: str
    file_name: str | None
    complete_list: bool
    is_correction: bool
    created_at: datetime
    decided_at: datetime | None
    created_by_name: str | None
    decided_by_name: str | None
    summary: dict[str, int] | None
    errors: int | None


class ChangesetOut(ChangesetSummaryOut):
    """A changeset with its validation report and items (the preview)."""

    licence: str
    attribution: str
    file_sha256: str | None
    decision_comment: str
    record_id: int | None
    report: dict[str, Any]
    items: list[ChangesetItemOut]
    installation_id: uuid.UUID | None = None
    submission_uuid: uuid.UUID | None = None
    submitted_by: str | None = None
    submitter_role: str | None = None
    base_package_version: str | None = None
    offline: bool = False
    review_started_at: datetime | None = None


class ApproveIn(BaseModel):
    """Approval of a changeset; a complete-list import repeats how many facilities close."""

    comment: str = ""
    confirm_close: int | None = Field(
        default=None, description="Number of facilities that will be closed (complete list)"
    )
    resolutions: dict[int, Literal["municipality", "hub"]] = Field(
        default_factory=dict,
        description="Per conflicting item number: apply the municipality's change or keep the "
        "hub's value (ADR 0014 A8)",
    )


class RejectIn(BaseModel):
    """Rejection of a changeset."""

    comment: str = ""


class ServiceInputs(BaseModel):
    """Capacity inputs of one service of a facility."""

    service_id: str
    places: float | None = None
    staff: float | None = None
    throughput: float | None = None
    throughput_unit: str | None = None


class FacilityEditIn(BaseModel):
    """A manual edit from the admin form: add, update or close one facility."""

    municipality_id: str
    facility_id: str | None = Field(default=None, description="Empty for a new facility")
    close: bool = False
    comment: str = ""
    values: dict[str, str | float | None] = Field(
        default_factory=dict,
        description="Template columns (name, facility_type, x, y, quality, …); omitted ones keep "
        "their current value",
    )
    services: list[ServiceInputs] = Field(default_factory=list)


class HistoryEntryOut(BaseModel):
    """One approved change of a facility."""

    changeset_id: int
    kind: str
    action: str
    fields: list[str]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    source: str
    comment: str
    file_name: str | None
    created_at: datetime
    created_by_name: str | None
    decided_at: datetime | None
    decided_by_name: str | None
    decision_comment: str


class StudyAreaIn(BaseModel):
    """A study area of an installation."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=1)
    core_municipalities: list[str] = Field(min_length=1)
    buffer_rule: Literal["whole_neighbouring_municipalities", "distance"] | None = None
    buffer_distance_m: float | None = Field(default=None, gt=0)


class PackageOut(BaseModel):
    """A package version of a study area."""

    id: int
    version: str
    status: Literal["building", "published", "failed"]
    bump: str
    created: date
    published_at: datetime | None
    archive_sha256: str | None
    bytes: int | None
    error: str | None
    job_id: str | None
    requested_at: datetime


class PendingOut(BaseModel):
    """What the next version would change (the propagation list's draft)."""

    last: dict[str, Any] | None
    features: dict[str, dict[str, list[str]]]
    coverage: list[dict[str, Any]]
    changed: bool
    changelog: str
    bump: str
    next_version: str


class StudyAreaOut(BaseModel):
    """A study area with its packages and whether an update is available."""

    id: str
    name: str
    core_municipalities: list[str]
    buffer_rule: str
    buffer_distance_m: float | None
    buffer_municipalities: list[str]
    last_version: str | None
    update_available: bool
    pending: PendingOut
    packages: list[PackageOut]


class PublishIn(BaseModel):
    """A request to publish the next version (an optional line added to the changelog)."""

    comment: str = ""


class PublishOut(BaseModel):
    """The queued package assembly."""

    package_id: int
    version: str
    job_id: str


# --- Installations and their submissions (ADR 0014 Part A) -----------------------------------


class InstallationIn(BaseModel):
    """Registration of a municipal installation."""

    name: str = Field(min_length=1, max_length=100)
    study_area_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")


class InstallationOut(BaseModel):
    """A registered installation (never its token)."""

    id: uuid.UUID
    name: str
    study_area_id: str
    study_area_registered: bool
    active: bool
    token_issued_at: datetime | None
    revoked_at: datetime | None
    last_contact_at: datetime | None
    last_contact_address: str | None
    created_at: datetime


class TokenOut(BaseModel):
    """A newly issued installation token, shown once."""

    installation: InstallationOut
    token: str = Field(description="Shown only now; store it as SOLIDARITYNODE_HUB_TOKEN")


class SubmissionRowIn(BaseModel):
    """One sanitised row of the import template."""

    row: int
    values: dict[str, str]


class SubmissionIn(BaseModel):
    """A submission sent by a municipal installation (personal data already dropped there)."""

    id: uuid.UUID
    municipality_id: str
    base_package_version: str
    file_name: str = ""
    comment: str = ""
    complete_list: bool = False
    is_correction: bool = False
    submitted_by: str = Field(pattern=r"^u-[0-9a-f]{8}$", description="Pseudonymous user id")
    submitter_role: Literal["analyst", "admin"]
    rows: list[SubmissionRowIn] = Field(max_length=5000)
    based_on: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per facility id: its state in the package the change was based on",
    )


class ConflictOut(BaseModel):
    """A conflicting item and how the hub resolved it."""

    facility_id: str | None
    fields: list[str]
    resolution: Literal["municipality", "hub"] | None


class SubmissionStatusOut(BaseModel):
    """The hub's view of one of the installation's submissions."""

    id: uuid.UUID
    changeset_id: int
    state: Literal["pending_review", "rejected_by_validation", "approved", "rejected", "withdrawn"]
    comment: str
    decided_at: datetime | None
    decided_by: str | None
    review_started: bool
    summary: dict[str, int] | None
    errors: int
    entries: list[CheckOut]
    conflicts: list[ConflictOut]


class InstallationPackageOut(BaseModel):
    """A published package version of the installation's study area."""

    version: str
    created: date
    published_at: datetime | None
    archive_sha256: str
    bytes: int
    changes: str
    changeset_ids: list[int]


class InstallationInfoOut(BaseModel):
    """What the installation's token gives access to."""

    installation_id: uuid.UUID
    installation: str
    study_area_id: str
    study_area_registered: bool
    core_municipalities: list[str]
    packages: list[InstallationPackageOut]
