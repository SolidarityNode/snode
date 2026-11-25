"""Scenarios: versioned, schema-validated overlays with owner and visibility (ADR 0016).

Counterfactual and disruption scenarios (Paper 1 §13, Paper 3 §7–10) as JSON overlays
(:class:`~solidaritynode_backend.schemas.scenario.ScenarioBody`). Every edit creates a new
immutable version; runs refer to versions. Visibility: ``private`` (owner and admins) or
``shared`` (every logged-in user). Delete is soft; a hard delete is refused when runs exist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import ValidationError
from solidaritynode_core.model import StudyArea
from solidaritynode_core.scenarios import check_references
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import CurrentUser, Principal
from solidaritynode_backend.db import get_session
from solidaritynode_backend.messages import msg
from solidaritynode_backend.orm import DataVersion, Job, Run, Scenario, ScenarioVersion, User
from solidaritynode_backend.schemas.api import (
    DataVersionRef,
    RunSummary,
    ScenarioIn,
    ScenarioListItem,
    ScenarioOut,
    ScenarioVersionOut,
    ValidationIssue,
    ValidationOut,
)
from solidaritynode_backend.schemas.scenario import ScenarioBody
from solidaritynode_backend.services.study_area import load_study_area

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

Db = Annotated[Session, Depends(get_session)]


def can_view(scenario: Scenario, user: Principal) -> bool:
    """Return whether ``user`` may see ``scenario``."""
    if scenario.deleted_at is not None:
        return False
    return user.is_admin or scenario.visibility == "shared" or scenario.owner_id == user.id


def can_edit(scenario: Scenario, user: Principal) -> bool:
    """Return whether ``user`` may edit, run or delete ``scenario``."""
    if scenario.is_baseline or scenario.deleted_at is not None or not user.can_edit:
        return False
    return user.is_admin or scenario.owner_id == user.id


def get_visible(db: Session, scenario_id: uuid.UUID, user: Principal) -> Scenario:
    """Return a scenario the user may see, or raise 404."""
    scenario = db.get(Scenario, scenario_id)
    if scenario is None or not can_view(scenario, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("error.scenario_not_found"))
    return scenario


def _require_editor(user: Principal) -> None:
    if not user.can_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, msg("error.requires_editor"))


def _active_dv(db: Session) -> DataVersion:
    dv = db.scalar(select(DataVersion).where(DataVersion.active))
    if dv is None:
        raise HTTPException(status.HTTP_409_CONFLICT, msg("error.no_data"))
    return dv


def _dv_ref(dv: DataVersion) -> DataVersionRef:
    return DataVersionRef(id=dv.id, package_id=dv.package_id, version=dv.version, active=dv.active)


class _Areas:
    """Study areas loaded once per request."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._cache: dict[int, StudyArea] = {}

    def problems(self, body: ScenarioBody, data_version_id: int) -> list[str]:
        if data_version_id not in self._cache:
            self._cache[data_version_id] = load_study_area(self._db, data_version_id)
        return check_references(self._cache[data_version_id], body.to_core("check", "check"))


def _usernames(db: Session) -> dict[int, str]:
    return {u.id: u.username for u in db.scalars(select(User))}


def _latest_run(
    db: Session, scenario_id: uuid.UUID, data_version_id: int | None, *, on: bool
) -> RunSummary | None:
    """Newest existing run of the scenario on (``on``) or off the given data version."""
    query = select(Run, Job).join(Job, Job.id == Run.job_id).where(Run.scenario_id == scenario_id)
    if data_version_id is not None:
        same = Run.data_version_id == data_version_id
        query = query.where(same if on else ~same)
    elif on:
        return None
    row = db.execute(query.order_by(Run.created_at.desc()).limit(1)).first()
    if row is None:
        return None
    run, job = row
    return RunSummary(
        id=run.id,
        status=job.status,
        progress=job.progress,
        data_version_id=run.data_version_id,
        package_version=run.package_version,
        created_at=run.created_at,
    )


def _version_out(
    db: Session, version: ScenarioVersion, names: dict[int, str]
) -> ScenarioVersionOut:
    dv = db.get(DataVersion, version.data_version_id)
    assert dv is not None
    return ScenarioVersionOut(
        scenario_id=version.scenario_id,
        version=version.version,
        name=version.name,
        description=version.description,
        schema_version=version.schema_version,
        body=ScenarioBody.model_validate(version.body),
        data_version=_dv_ref(dv),
        created_at=version.created_at,
        created_by=names.get(version.created_by) if version.created_by else None,
    )


def _item(
    db: Session,
    scenario: Scenario,
    version: ScenarioVersion,
    user: Principal,
    names: dict[int, str],
    areas: _Areas,
    active: DataVersion | None,
) -> dict[str, Any]:
    dv = db.get(DataVersion, version.data_version_id)
    assert dv is not None
    body = ScenarioBody.model_validate(version.body)
    active_id = active.id if active else None
    return {
        "id": scenario.id,
        "name": version.name,
        "description": version.description,
        "visibility": scenario.visibility,
        "owner": names.get(scenario.owner_id) if scenario.owner_id else None,
        "owner_id": scenario.owner_id,
        "is_baseline": scenario.is_baseline,
        "latest_version": scenario.latest_version,
        "data_version": _dv_ref(dv),
        "updated_at": scenario.updated_at,
        "latest_run": (latest := _latest_run(db, scenario.id, active_id, on=True)),
        "latest_run_other_data": None
        if latest
        else _latest_run(db, scenario.id, active_id, on=False),
        "problems": areas.problems(body, active.id) if active and not scenario.is_baseline else [],
        "can_edit": can_edit(scenario, user),
    }


def _latest(db: Session, scenario: Scenario) -> ScenarioVersion:
    version = db.get(ScenarioVersion, (scenario.id, scenario.latest_version))
    assert version is not None
    return version


def _scenario_out(db: Session, scenario: Scenario, user: Principal) -> ScenarioOut:
    names = _usernames(db)
    version = _latest(db, scenario)
    active = db.scalar(select(DataVersion).where(DataVersion.active))
    versions = list(
        db.scalars(
            select(ScenarioVersion.version)
            .where(ScenarioVersion.scenario_id == scenario.id)
            .order_by(ScenarioVersion.version)
        )
    )
    return ScenarioOut(
        **_item(db, scenario, version, user, names, _Areas(db), active),
        current=_version_out(db, version, names),
        versions=versions,
        created_at=scenario.created_at,
    )


@router.get("", response_model=list[ScenarioListItem])
def list_scenarios(
    user: CurrentUser,
    db: Db,
    owner: Annotated[Literal["me", "others", "all"], Query()] = "all",
    visibility: Annotated[Literal["private", "shared"] | None, Query()] = None,
) -> list[ScenarioListItem]:
    """List the scenarios the user may see, with the status of each one's latest run.

    ``problems`` lists references that do not resolve against the active data version (closed
    or missing features), so scenarios made on an older version are revalidated.
    """
    names = _usernames(db)
    areas = _Areas(db)
    active = db.scalar(select(DataVersion).where(DataVersion.active))
    out = []
    for scenario in db.scalars(
        select(Scenario).where(Scenario.deleted_at.is_(None)).order_by(Scenario.updated_at.desc())
    ):
        if not can_view(scenario, user):
            continue
        if owner == "me" and scenario.owner_id != user.id:
            continue
        if owner == "others" and scenario.owner_id == user.id:
            continue
        if visibility and scenario.visibility != visibility:
            continue
        out.append(
            ScenarioListItem(
                **_item(db, scenario, _latest(db, scenario), user, names, areas, active)
            )
        )
    return out


@router.post("/validate", response_model=ValidationOut)
def validate_scenario(
    user: CurrentUser, db: Db, payload: Annotated[dict[str, Any], Body()]
) -> ValidationOut:
    """Validate a scenario (schema and references against the active data) without saving it."""
    try:
        parsed = ScenarioIn.model_validate(payload)
    except ValidationError as exc:
        errors = [
            ValidationIssue(loc=[str(p) for p in e["loc"]], msg=e["msg"]) for e in exc.errors()
        ]
        return ValidationOut(valid=False, errors=errors, problems=[])
    dv = db.scalar(select(DataVersion).where(DataVersion.active))
    problems = _Areas(db).problems(parsed.body, dv.id) if dv else [msg("error.no_data")]
    return ValidationOut(valid=not problems, errors=[], problems=problems)


def _check_or_422(db: Session, body: ScenarioBody, dv: DataVersion) -> None:
    if problems := _Areas(db).problems(body, dv.id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": msg("error.scenario_mismatch"), "problems": problems},
        )


@router.post("", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def create_scenario(body: ScenarioIn, user: CurrentUser, db: Db) -> ScenarioOut:
    """Create a scenario (version 1) against the active data version."""
    _require_editor(user)
    dv = _active_dv(db)
    _check_or_422(db, body.body, dv)
    scenario = Scenario(
        id=uuid.uuid4(), owner_id=user.id, visibility=body.visibility, latest_version=1
    )
    db.add(scenario)
    db.flush()
    db.add(
        ScenarioVersion(
            scenario_id=scenario.id,
            version=1,
            name=body.name,
            description=body.description,
            schema_version=body.body.schema_version,
            body=body.body.model_dump(),
            data_version_id=dv.id,
            created_by=user.id,
        )
    )
    db.commit()
    return _scenario_out(db, scenario, user)


@router.get("/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: uuid.UUID, user: CurrentUser, db: Db) -> ScenarioOut:
    """Return a scenario with its latest version."""
    return _scenario_out(db, get_visible(db, scenario_id, user), user)


@router.get("/{scenario_id}/versions/{version}", response_model=ScenarioVersionOut)
def get_version(
    scenario_id: uuid.UUID, version: int, user: CurrentUser, db: Db
) -> ScenarioVersionOut:
    """Return one version (old versions stay readable because runs refer to them)."""
    get_visible(db, scenario_id, user)
    row = db.get(ScenarioVersion, (scenario_id, version))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("error.version_not_found"))
    return _version_out(db, row, _usernames(db))


@router.get("/{scenario_id}/check", response_model=ValidationOut)
def check_scenario(
    scenario_id: uuid.UUID,
    user: CurrentUser,
    db: Db,
    data_version_id: Annotated[int | None, Query()] = None,
) -> ValidationOut:
    """Revalidate the latest version against a data version (default: the active one)."""
    scenario = get_visible(db, scenario_id, user)
    dv = db.get(DataVersion, data_version_id) if data_version_id else _active_dv(db)
    if dv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("error.data_version_not_found"))
    body = ScenarioBody.model_validate(_latest(db, scenario).body)
    problems = _Areas(db).problems(body, dv.id)
    return ValidationOut(valid=not problems, errors=[], problems=problems)


@router.put("/{scenario_id}", response_model=ScenarioOut)
def update_scenario(
    scenario_id: uuid.UUID, body: ScenarioIn, user: CurrentUser, db: Db
) -> ScenarioOut:
    """Save a new version (against the active data version); earlier versions stay."""
    scenario = get_visible(db, scenario_id, user)
    if not can_edit(scenario, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, msg("error.only_owner_edit"))
    dv = _active_dv(db)
    _check_or_422(db, body.body, dv)
    scenario.latest_version += 1
    scenario.visibility = body.visibility
    scenario.updated_at = datetime.now(UTC)
    db.add(
        ScenarioVersion(
            scenario_id=scenario.id,
            version=scenario.latest_version,
            name=body.name,
            description=body.description,
            schema_version=body.body.schema_version,
            body=body.body.model_dump(),
            data_version_id=dv.id,
            created_by=user.id,
        )
    )
    db.commit()
    return _scenario_out(db, scenario, user)


@router.post(
    "/{scenario_id}/duplicate", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED
)
def duplicate_scenario(scenario_id: uuid.UUID, user: CurrentUser, db: Db) -> ScenarioOut:
    """Copy the latest version into a new private scenario owned by the user."""
    _require_editor(user)
    source = get_visible(db, scenario_id, user)
    latest = _latest(db, source)
    dv = _active_dv(db)
    copy = Scenario(id=uuid.uuid4(), owner_id=user.id, visibility="private", latest_version=1)
    db.add(copy)
    db.flush()
    db.add(
        ScenarioVersion(
            scenario_id=copy.id,
            version=1,
            name=f"Copy of {latest.name}",
            description=latest.description,
            schema_version=latest.schema_version,
            body=latest.body,
            data_version_id=dv.id,
            created_by=user.id,
        )
    )
    db.commit()
    return _scenario_out(db, copy, user)


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "Hard delete refused: runs exist"}},
)
def delete_scenario(
    scenario_id: uuid.UUID,
    user: CurrentUser,
    db: Db,
    hard: Annotated[bool, Query()] = False,
) -> None:
    """Soft-delete a scenario (runs keep it). ``hard=true`` deletes it only if it has no runs."""
    scenario = get_visible(db, scenario_id, user)
    if not can_edit(scenario, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, msg("error.only_owner_delete"))
    if hard:
        runs = db.scalar(
            select(func.count()).select_from(Run).where(Run.scenario_id == scenario.id)
        )
        if runs:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                msg("error.hard_delete_has_runs", runs=runs),
            )
        db.execute(delete(ScenarioVersion).where(ScenarioVersion.scenario_id == scenario.id))
        db.delete(scenario)
    else:
        scenario.deleted_at = datetime.now(UTC)
    db.commit()
