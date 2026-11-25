"""Request and response models of the HTTP API (the frontend types are generated from them)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from solidaritynode_backend.schemas.scenario import ScenarioBody

__all__ = [
    "AppConfigOut",
    "CatalogOut",
    "CompareOut",
    "CompareRow",
    "CoverageOut",
    "DataVersionOut",
    "ImportIn",
    "ImportOut",
    "IndicatorOut",
    "LoginIn",
    "PreviewIn",
    "PreviewOut",
    "ResultRow",
    "RunConfigIn",
    "RunIn",
    "RunOut",
    "ScenarioIn",
    "ScenarioListItem",
    "ScenarioOut",
    "ScenarioVersionOut",
    "UserIn",
    "UserOut",
    "UserPatch",
    "ValidationIssue",
    "ValidationOut",
]

Role = Literal["admin", "analyst", "viewer"]
Visibility = Literal["private", "shared"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- auth and users ---


class LoginIn(_In):
    """Credentials."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    """A user account (never includes the password hash)."""

    id: int
    username: str
    role: Role
    active: bool


class UserIn(_In):
    """New user."""

    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    password: str = Field(min_length=12, max_length=256)
    role: Role


class UserPatch(_In):
    """Change a user's role, status or password."""

    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)


class AppConfigOut(BaseModel):
    """Public configuration the frontend needs before login."""

    deployment_mode: Literal["municipality", "hub"]
    basemap: Literal["osm", "blank"]
    app_env: str
    version: str
    git_commit: str
    diagnostic_label: str
    docs_url: str = Field(
        description="User guide matching the running version (SOLIDARITYNODE_DOCS_BASE_URL + "
        "major.minor, or dev in development)"
    )


# --- data versions and packages ---


class CoverageOut(BaseModel):
    """Status of one layer for one municipality."""

    municipality_id: str
    layer: str
    status: Literal["missing", "open_data", "estimated", "verified_by_municipality"]
    layer_version: str


class LayerLicenceOut(BaseModel):
    """Licence and attribution of one layer of a data package (ADR 0013)."""

    layer: str
    licence: str
    attribution: str


class DataVersionOut(BaseModel):
    """An imported data package version."""

    id: int
    package_id: str
    version: str
    schema_version: str
    created: date
    active: bool
    imported_at: datetime
    synthetic: bool
    study_area: dict[str, Any]
    changelog: list[dict[str, Any]]
    processing_notes: list[str]
    sources: list[dict[str, Any]]
    layer_licences: list[LayerLicenceOut] = Field(
        default_factory=list, description="Licence and attribution per layer (schema 2.0)"
    )
    coverage: list[CoverageOut]
    edge_effect_units: list[str]


class GroupOut(BaseModel):
    """A population group of a data version (never a measure of need; OQ-6)."""

    group_id: str
    name: str
    definition_rule: str


class ServiceOut(BaseModel):
    """A service of a data version with its service unit (OQ-24)."""

    service_id: str
    name: str
    service_unit: str
    max_acceptable_wait: str | None = None


class CatalogOut(BaseModel):
    """Groups and services of a data version."""

    groups: list[GroupOut]
    services: list[ServiceOut]


class AvailablePackage(BaseModel):
    """A package offered for import from the server's package directory."""

    name: str
    package_id: str | None
    version: str | None
    created: str | None


class PreviewIn(_In):
    """Preview a package available on the server."""

    name: str


class FieldChange(BaseModel):
    """A feature whose attributes or geometry changed."""

    id: str
    fields: list[str]


class LayerDiff(BaseModel):
    """Changes in one layer against the active version."""

    added: list[str]
    changed: list[FieldChange]
    closed: list[str]
    removed: list[str]
    unchanged: int
    total: int


class CoverageChange(BaseModel):
    """A coverage status that changes."""

    municipality_id: str
    layer: str
    before: str | None
    after: str


class PreviewOut(BaseModel):
    """Preview of a package import; nothing has been written yet."""

    staging_id: str | None = None
    source: str
    package_id: str
    version: str
    schema_version: str
    created: str
    synthetic: bool
    changelog: list[dict[str, Any]]
    active: dict[str, str] | None
    status: Literal["new", "update", "same_version", "conflict", "other_package"]
    layers: dict[str, LayerDiff]
    coverage_changes: list[CoverageChange]
    problems: list[str]
    warnings: list[str]


class ImportIn(_In):
    """Confirm an import previewed before: either a server package name or a staging id."""

    name: str | None = None
    staging_id: str | None = None


class RevalidationOut(BaseModel):
    """A scenario whose references do not resolve against a data version."""

    scenario_id: str
    name: str
    problems: list[str]


class ImportOut(BaseModel):
    """Outcome of an import."""

    data_version_id: int
    noop: bool
    baseline_run_id: str | None
    revalidation: list[RevalidationOut]


# --- scenarios ---


class ScenarioIn(_In):
    """Create a scenario, or save a new version of it."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    visibility: Visibility = "private"
    body: ScenarioBody = Field(default_factory=ScenarioBody)


class DataVersionRef(BaseModel):
    """Short reference to a data version."""

    id: int
    package_id: str
    version: str
    active: bool


class RunSummary(BaseModel):
    """Status of one run of a scenario (an existing run: its id can always be opened)."""

    id: uuid.UUID
    status: RunStatus
    progress: float
    data_version_id: int
    package_version: str
    created_at: datetime


class ScenarioListItem(BaseModel):
    """A scenario in the list."""

    id: uuid.UUID
    name: str
    description: str
    visibility: Visibility
    owner: str | None
    owner_id: int | None
    is_baseline: bool
    latest_version: int
    data_version: DataVersionRef
    updated_at: datetime
    latest_run: RunSummary | None = Field(
        description="Newest run on the active data version; null if there is none"
    )
    latest_run_other_data: RunSummary | None = Field(
        description="Newest run on any other data version, only when there is no run on the "
        "active one (the list then says 'Latest run on data X')"
    )
    problems: list[str]
    can_edit: bool


class ScenarioVersionOut(BaseModel):
    """One immutable version of a scenario."""

    scenario_id: uuid.UUID
    version: int
    name: str
    description: str
    schema_version: str
    body: ScenarioBody
    data_version: DataVersionRef
    created_at: datetime
    created_by: str | None


class ScenarioOut(ScenarioListItem):
    """A scenario with its latest version and the list of versions."""

    current: ScenarioVersionOut
    versions: list[int]
    created_at: datetime


class ValidationIssue(BaseModel):
    """One validation error."""

    loc: list[str]
    msg: str


class ValidationOut(BaseModel):
    """Result of validating a scenario without saving it."""

    valid: bool
    errors: list[ValidationIssue]
    problems: list[str]


# --- runs ---


class RunConfigIn(_In):
    """Run configuration (recorded on the run and part of its input hash)."""

    n_samples: int | None = Field(default=None, ge=1, le=10_000)
    step_delay_s: float | None = Field(default=None, ge=0, le=60)


class RunIn(_In):
    """Start a run."""

    scenario_id: uuid.UUID
    scenario_version: int | None = None
    data_version_id: int | None = None
    seed: int | None = Field(
        default=None,
        ge=0,
        le=2**31 - 1,
        description="Random seed; when omitted one is drawn and recorded (seed_source: drawn)",
    )
    config: RunConfigIn = Field(default_factory=RunConfigIn)
    force: bool = False


class IndicatorOut(BaseModel):
    """Description of an output indicator."""

    id: str
    label: str
    unit: str
    deterministic: bool
    group_dependent: bool


class RunOut(BaseModel):
    """A run with every reproducibility field and its lifecycle."""

    id: uuid.UUID
    scenario_id: uuid.UUID
    scenario_version: int
    scenario_name: str
    is_baseline: bool
    data_version_id: int
    package_id: str
    package_version: str
    code_version: str
    model_id: str
    model_version: str
    diagnostic: bool
    seed: int
    config: dict[str, Any]
    input_hash: str
    status: RunStatus
    progress: float
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_by: str | None
    reused: bool = False
    indicators: list[IndicatorOut]
    diagnostics: dict[str, Any] | None
    edge_effect_units: list[str]
    can_cancel: bool
    interval_quantiles: list[float] | None = Field(
        default=None,
        description="Quantile levels of every result's low and high bounds (for example "
        "[0.05, 0.95], a 90 % interval); null for runs recorded before they were stored.",
    )
    samples_sha256: str | None = Field(
        default=None, description="SHA-256 of the samples Parquet file (verified on export)"
    )
    samples_estimate_bytes: int | None = Field(
        default=None,
        description="Estimated samples file size before compression, computed before the run",
    )
    samples_limit_bytes: int | None = Field(
        default=None, description="Warning limit for the samples file in force at creation"
    )
    seed_source: Literal["given", "drawn"] = Field(
        default="given", description="Whether the seed was given or drawn because none was"
    )
    code_version_dirty: bool = Field(
        default=False,
        description="The code version has uncommitted changes (-dirty) or is unknown: the run is "
        "reproducible only on the machine that made it",
    )
    environment: dict[str, str] | None = Field(
        default=None,
        description="Platform (SolidarityNode), Python and NumPy versions and the OS of the worker "
        "(not in the hash)",
    )
    reuse_refused: str | None = Field(
        default=None,
        description="Why a matching earlier run was not reused (its results file failed the "
        "integrity check)",
    )


class ResultRow(BaseModel):
    """Summary statistics of one indicator for ``unit × group × service × time`` (ADR 0017).

    ``median`` is the central value shown on maps and tables; ``low`` and ``high`` are the
    quantiles given by the run's ``interval_quantiles``; ``mean`` is stored and exported.
    """

    unit_id: str
    unit_name: str
    group_id: str
    service_id: str
    time_label: str
    indicator: str
    mean: float | None
    median: float | None
    low: float | None
    high: float | None
    baseline: float | None
    edge_effect_warning: bool


class IntervalOut(BaseModel):
    """Summary statistics of one value: mean, median and interval bounds."""

    mean: float | None
    median: float | None
    low: float | None
    high: float | None


class CompareRow(BaseModel):
    """Two runs side by side for one cell."""

    unit_id: str
    unit_name: str
    group_id: str
    service_id: str
    indicator: str
    a: IntervalOut
    b: IntervalOut
    difference_of_medians: float | None = Field(
        description="Difference of the medians, A − B (not a difference of draws; ADR 0017)"
    )
    edge_effect_warning: bool


class CompareOut(BaseModel):
    """Comparison of run ``a`` (scenario) with run ``b`` (baseline or another run)."""

    run_a: RunOut
    run_b: RunOut
    cross_data_version: bool
    label: str
    rows: list[CompareRow]


class RoleFeatureOut(BaseModel):
    """State of a role-specific feature (ADR 0012)."""

    role: Literal["municipality", "hub"]
    feature: str
    implemented: bool
    note: str


class StorageOut(BaseModel):
    """Disk usage of the results volume (admin; ADR 0017)."""

    results_dir: str
    runs_with_samples: int
    samples_files: int
    samples_bytes: int
    total_bytes: int | None
    free_bytes: int | None
