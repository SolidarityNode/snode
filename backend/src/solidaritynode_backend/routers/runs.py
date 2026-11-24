"""Runs: start (as background jobs), follow, cancel, read results, compare and export.

Request handlers never compute: starting a run only queues a job for the worker (AGENTS.md,
ADR 0006). Runs are immutable and record every reproducibility field (ADR 0017). Results are
visible to whoever may see the run's scenario. Comparison is allowed between runs on the same
data version, or between two runs of the same scenario across data versions (labelled as such).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from solidaritynode_core.model import get_registry
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import CurrentUser, Principal
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.jobs import JobStatus, PostgresJobRunner
from solidaritynode_backend.orm import DataVersion, Job, Run, Scenario, ScenarioVersion, User
from solidaritynode_backend.routers.scenarios import can_edit, can_view, get_visible
from solidaritynode_backend.schemas.api import (
    CompareOut,
    CompareRow,
    IndicatorOut,
    IntervalOut,
    ResultRow,
    RunIn,
    RunOut,
)
from solidaritynode_backend.services.export import export_csv, export_gpkg
from solidaritynode_backend.services.runs import RunInputError, create_run

router = APIRouter(prefix="/runs", tags=["runs"])

Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


def run_out(db: Session, run: Run, user: Principal, *, reused: bool = False) -> RunOut:
    """Build the API view of a run."""
    job = db.get(Job, run.job_id)
    assert job is not None
    db.refresh(job)
    version = db.get(ScenarioVersion, (run.scenario_id, run.scenario_version))
    scenario = db.get(Scenario, run.scenario_id)
    assert version is not None
    assert scenario is not None
    creator = db.get(User, run.created_by) if run.created_by else None
    warned = sorted(
        {
            r[0]
            for r in db.execute(
                text("SELECT unit_id FROM data_warnings WHERE data_version_id = :dv"),
                {"dv": run.data_version_id},
            )
        }
    )
    try:
        diagnostic = get_registry().get(run.model_id).diagnostic
    except KeyError:
        diagnostic = True
    status_ = JobStatus(job.status)
    return RunOut(
        id=run.id,
        scenario_id=run.scenario_id,
        scenario_version=run.scenario_version,
        scenario_name=version.name,
        is_baseline=run.is_baseline,
        data_version_id=run.data_version_id,
        package_id=run.package_id,
        package_version=run.package_version,
        code_version=run.code_version,
        model_id=run.model_id,
        model_version=run.model_version,
        diagnostic=diagnostic,
        seed=run.seed,
        config=run.config,
        input_hash=run.input_hash,
        status=status_.value,
        progress=job.progress,
        error=job.error,
        created_at=run.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_by=creator.username if creator else None,
        reused=reused,
        indicators=[IndicatorOut(**i) for i in run.indicators or []],
        diagnostics=run.diagnostics,
        edge_effect_units=warned,
        can_cancel=not status_.finished
        and (user.is_admin or (user.can_edit and run.created_by == user.id)),
    )


def get_visible_run(db: Session, run_id: uuid.UUID, user: Principal) -> Run:
    """Return a run whose scenario the user may see, or raise 404."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    scenario = db.get(Scenario, run.scenario_id)
    if scenario is None or not (can_view(scenario, user) or (user.is_admin)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@router.post(
    "",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "A succeeded run with the same inputs was reused", "model": RunOut},
        422: {"description": "The scenario does not resolve against the data version"},
    },
)
def start_run(
    body: RunIn, user: CurrentUser, db: Db, settings: Config, response: Response
) -> RunOut:
    """Queue a run of a scenario version on a data version (defaults: latest, active).

    If a succeeded run has the same input hash it is returned (``reused``) unless ``force``.
    """
    scenario = get_visible(db, body.scenario_id, user)
    if not (can_edit(scenario, user) or (scenario.is_baseline and user.can_edit)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner or an admin can run it")
    version = db.get(
        ScenarioVersion, (scenario.id, body.scenario_version or scenario.latest_version)
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario version not found")
    if body.data_version_id is not None:
        dv = db.get(DataVersion, body.data_version_id)
    else:
        dv = db.scalar(select(DataVersion).where(DataVersion.active))
    if dv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "data version not found")
    config = body.config.model_dump(exclude_none=True)
    try:
        created = create_run(
            db,
            settings,
            scenario,
            version,
            dv,
            seed=body.seed,
            config=config,
            created_by=user.id,
            force=body.force,
        )
    except RunInputError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "message": f"the scenario does not match data {dv.version}",
                "problems": exc.problems,
            },
        ) from None
    db.commit()
    if created.reused:
        response.status_code = status.HTTP_200_OK
    return run_out(db, created.run, user, reused=created.reused)


@router.get("", response_model=list[RunOut])
def list_runs(
    user: CurrentUser,
    db: Db,
    scenario_id: Annotated[uuid.UUID | None, Query()] = None,
    data_version_id: Annotated[int | None, Query()] = None,
    baseline: Annotated[bool | None, Query()] = None,
) -> list[RunOut]:
    """List visible runs, newest first."""
    query = select(Run).order_by(Run.created_at.desc())
    if scenario_id:
        query = query.where(Run.scenario_id == scenario_id)
    if data_version_id:
        query = query.where(Run.data_version_id == data_version_id)
    if baseline is not None:
        query = query.where(Run.is_baseline == baseline)
    out = []
    for run in db.scalars(query.limit(200)):
        scenario = db.get(Scenario, run.scenario_id)
        if scenario and (can_view(scenario, user) or user.is_admin):
            out.append(run_out(db, run, user))
    return out


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, user: CurrentUser, db: Db) -> RunOut:
    """Return a run with its status and progress."""
    return run_out(db, get_visible_run(db, run_id, user), user)


@router.post("/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: uuid.UUID, user: CurrentUser, db: Db) -> RunOut:
    """Cancel a queued run at once, or a running one at its next progress step."""
    run = get_visible_run(db, run_id, user)
    if not (user.is_admin or (user.can_edit and run.created_by == user.id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only who started the run or an admin")
    PostgresJobRunner(db).cancel(str(run.job_id))
    db.commit()
    return run_out(db, run, user)


def _require_succeeded(db: Session, run: Run) -> None:
    job = db.get(Job, run.job_id)
    if job is None or job.status != JobStatus.SUCCEEDED:
        raise HTTPException(status.HTTP_409_CONFLICT, "the run has no results (not succeeded)")


def _results(
    db: Session,
    run: Run,
    group: str | None = None,
    service: str | None = None,
    indicator: str | None = None,
) -> list[ResultRow]:
    rows = db.execute(
        text(
            """
            SELECT r.unit_id, coalesce(f.properties->>'name', r.unit_id) AS unit_name,
                   r.group_id, r.service_id, r.time_label, r.indicator, r.value, r.low, r.high,
                   r.baseline, r.edge_effect_warning
            FROM run_results r
            LEFT JOIN data_features f ON f.data_version_id = :dv AND f.layer = 'spatial_units'
                 AND f.feature_id = r.unit_id
            WHERE r.run_id = :run
              AND (CAST(:g AS text) IS NULL OR r.group_id = :g)
              AND (CAST(:s AS text) IS NULL OR r.service_id = :s)
              AND (CAST(:i AS text) IS NULL OR r.indicator = :i)
            ORDER BY r.unit_id, r.group_id, r.service_id, r.indicator
            """
        ),
        {"run": run.id, "dv": run.data_version_id, "g": group, "s": service, "i": indicator},
    ).mappings()
    return [ResultRow(**row) for row in rows]


@router.get("/{run_id}/results", response_model=list[ResultRow])
def run_results(
    run_id: uuid.UUID,
    user: CurrentUser,
    db: Db,
    group: Annotated[str | None, Query()] = None,
    service: Annotated[str | None, Query()] = None,
    indicator: Annotated[str | None, Query()] = None,
) -> list[ResultRow]:
    """Summary values per ``unit × group × service × time`` (core units only)."""
    run = get_visible_run(db, run_id, user)
    _require_succeeded(db, run)
    return _results(db, run, group, service, indicator)


@router.get("/{run_id}/tables/{name}")
def run_table(
    run_id: uuid.UUID, name: Literal["travel_times", "unit_changes"], user: CurrentUser, db: Db
) -> list[dict[str, object]]:
    """Model tables: ``travel_times`` (before/after, hand-check) and ``unit_changes``."""
    run = get_visible_run(db, run_id, user)
    _require_succeeded(db, run)
    rows = db.scalar(
        text("SELECT rows FROM run_tables WHERE run_id = :r AND table_name = :n"),
        {"r": run.id, "n": name},
    )
    return list(rows or [])


@router.get(
    "/{run_id}/compare",
    response_model=CompareOut,
    responses={409: {"description": "Runs on different data versions of different scenarios"}},
)
def compare_runs(
    run_id: uuid.UUID,
    user: CurrentUser,
    db: Db,
    other: Annotated[uuid.UUID | None, Query(alias="with")] = None,
) -> CompareOut:
    """Compare a run with the baseline run of its data version, or with another run.

    Runs on different data versions are compared only if they belong to the same scenario; the
    result is then labelled as a cross-data-version comparison.
    """
    a = get_visible_run(db, run_id, user)
    _require_succeeded(db, a)
    if other is None:
        b = db.scalar(
            select(Run)
            .join(Job, Job.id == Run.job_id)
            .where(
                Run.is_baseline,
                Run.data_version_id == a.data_version_id,
                Job.status == JobStatus.SUCCEEDED,
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        if b is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"no succeeded baseline run on data {a.package_version} yet",
            )
    else:
        b = get_visible_run(db, other, user)
        _require_succeeded(db, b)
    cross = a.data_version_id != b.data_version_id
    if cross and a.scenario_id != b.scenario_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"the runs use different data versions ({a.package_version} and "
            f"{b.package_version}); compare runs on the same data version, or two runs of "
            "the same scenario",
        )
    rows_b = {(r.unit_id, r.group_id, r.service_id, r.indicator): r for r in _results(db, b)}
    rows = []
    for r in _results(db, a):
        o = rows_b.get((r.unit_id, r.group_id, r.service_id, r.indicator))
        diff = r.value - o.value if (o and r.value is not None and o.value is not None) else None
        rows.append(
            CompareRow(
                unit_id=r.unit_id,
                unit_name=r.unit_name,
                group_id=r.group_id,
                service_id=r.service_id,
                indicator=r.indicator,
                a=IntervalOut(value=r.value, low=r.low, high=r.high),
                b=IntervalOut(
                    value=o.value if o else None,
                    low=o.low if o else None,
                    high=o.high if o else None,
                ),
                difference=diff,
                edge_effect_warning=r.edge_effect_warning or bool(o and o.edge_effect_warning),
            )
        )
    label = (
        f"Same scenario across data versions {b.package_version} → {a.package_version}"
        if cross
        else f"Same data version {a.package_version}"
    )
    return CompareOut(
        run_a=run_out(db, a, user),
        run_b=run_out(db, b, user),
        cross_data_version=cross,
        label=label,
        rows=rows,
    )


@router.get(
    "/{run_id}/export",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}, "description": "Zip archive"}},
)
def export_run(
    run_id: uuid.UUID,
    user: CurrentUser,
    db: Db,
    format: Annotated[Literal["csv", "gpkg"], Query()] = "csv",
) -> Response:
    """Export results as CSV or GeoPackage in a zip, with ``metadata.json`` (reproducibility)."""
    run = get_visible_run(db, run_id, user)
    _require_succeeded(db, run)
    meta = run_out(db, run, user).model_dump(mode="json", exclude={"can_cancel", "reused"})
    rows = [r.model_dump() for r in _results(db, run)]
    data = export_csv(db, run, meta, rows) if format == "csv" else export_gpkg(db, run, meta, rows)
    filename = f"run-{run.id}-{format}.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
