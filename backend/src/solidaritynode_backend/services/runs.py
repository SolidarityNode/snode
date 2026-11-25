"""Runs: creation with an input hash, cached reuse, and execution in the worker (ADR 0017).

A run is **immutable** and records every reproducibility field: scenario id and version, data
package id and version, code version (git commit), model id and version, random seed and
configuration. Its lifecycle (``queued → running → succeeded | failed | cancelled``, progress,
error) lives in its job (ADR 0006). The **input hash** covers every recorded input except
timestamps; starting a run whose hash matches a succeeded run returns that run unless a rerun is
forced.

Results: per ``unit × group × service × time``, the **mean**, the **median** and the interval
bounds at the quantile levels of the run configuration (``interval_quantiles``, default 5 % and
95 %) in PostgreSQL (``run_results``), computed from the model's samples by
:func:`solidaritynode_core.uncertainty.summarise_result` (ADR 0017); per-sample values in Parquet
under ``results_dir`` (ADR 0008), model tables in ``run_tables``. Totals across units or groups
are computed from the samples, never by adding medians.
Results are stored for **core units only** (OQ-28); units with an edge-effect warning are
flagged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from solidaritynode_core.model import get_registry
from solidaritynode_core.scenarios import check_references
from solidaritynode_core.uncertainty import DEFAULT_INTERVAL, summarise_result
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.jobs import JobContext, PostgresJobRunner
from solidaritynode_backend.orm import DataVersion, Job, Run, Scenario, ScenarioVersion
from solidaritynode_backend.schemas.scenario import ScenarioBody
from solidaritynode_backend.services.samples import (
    as_stored,
    estimate_samples_bytes,
    write_samples,
)
from solidaritynode_backend.services.study_area import load_study_area

__all__ = [
    "DEFAULT_MODEL_ID",
    "DEFAULT_SEED",
    "RUN_JOB_KIND",
    "CreatedRun",
    "RunInputError",
    "create_run",
    "execute_run",
    "input_hash",
    "reference_problems",
]

DEFAULT_MODEL_ID = "diagnostic-v0"
DEFAULT_SEED = 1
RUN_JOB_KIND = "run"

log = logging.getLogger("solidaritynode.runs")


class RunInputError(ValueError):
    """The run cannot start: the scenario does not resolve against the data version."""

    def __init__(self, problems: list[str]) -> None:
        """Keep the problems for the API response."""
        super().__init__("; ".join(problems))
        self.problems = problems


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def input_hash(fields: Mapping[str, Any]) -> str:
    """Return the SHA-256 of the canonical JSON of the run inputs (no timestamps)."""
    return hashlib.sha256(_canonical(dict(fields))).hexdigest()


def reference_problems(db: Session, body: ScenarioBody, data_version_id: int) -> list[str]:
    """Return references of ``body`` that do not resolve in a data version (closed or missing)."""
    area = load_study_area(db, data_version_id)
    return check_references(area, body.to_core("check", "check"))


@dataclass(frozen=True, slots=True)
class CreatedRun:
    """Outcome of :func:`create_run`."""

    run: Run
    reused: bool


def create_run(
    db: Session,
    settings: Settings,
    scenario: Scenario,
    version: ScenarioVersion,
    data_version: DataVersion,
    *,
    seed: int = DEFAULT_SEED,
    config: Mapping[str, Any] | None = None,
    created_by: int | None = None,
    force: bool = False,
) -> CreatedRun:
    """Queue a run, or return the succeeded run with the same input hash (caller commits).

    Raises:
        RunInputError: If the scenario references closed or missing features of the data
            version (reported, never silently dropped).
    """
    body = ScenarioBody.model_validate(version.body)
    if problems := reference_problems(db, body, data_version.id):
        raise RunInputError(problems)
    model = get_registry().get(DEFAULT_MODEL_ID)
    full_config = {
        **model.default_config,
        "step_delay_s": settings.diagnostic_step_delay_s,
        "interval_quantiles": list(settings.interval_quantiles()),
        **(config or {}),
    }
    fields = {
        "scenario_id": str(scenario.id),
        "scenario_version": version.version,
        "scenario_body": version.body,
        "package_id": data_version.package_id,
        "package_version": data_version.version,
        "package_manifest_sha256": data_version.manifest_sha256,
        "code_version": settings.git_commit,
        "model_id": model.id,
        "model_version": model.version,
        "seed": seed,
        "config": full_config,
    }
    digest = input_hash(fields)
    if not force:
        existing = db.scalar(
            select(Run)
            .join(Job, Job.id == Run.job_id)
            .where(Run.input_hash == digest, Job.status == "succeeded")
            .order_by(Run.created_at)
            .limit(1)
        )
        if existing is not None:
            return CreatedRun(existing, reused=True)
    run_id = uuid.uuid4()
    # Estimate the samples file before the run starts; a run above the limit is still queued, and
    # the run page warns (ADR 0008).
    estimate = estimate_samples_bytes(
        db, model, data_version.id, int(full_config.get("n_samples", 0))
    )
    limit = int(settings.samples_warn_mb * 1_000_000)
    if estimate > limit:
        log.warning(
            "run %s: samples file estimated at %d bytes, above the limit of %d bytes",
            run_id,
            estimate,
            limit,
        )
    job_id = PostgresJobRunner(db).submit(RUN_JOB_KIND, {"run_id": str(run_id)})
    run = Run(
        id=run_id,
        scenario_id=scenario.id,
        scenario_version=version.version,
        data_version_id=data_version.id,
        package_id=data_version.package_id,
        package_version=data_version.version,
        code_version=settings.git_commit,
        model_id=model.id,
        model_version=model.version,
        seed=seed,
        config=full_config,
        input_hash=digest,
        is_baseline=scenario.is_baseline,
        job_id=uuid.UUID(job_id),
        created_by=created_by,
        samples_estimate_bytes=estimate,
        samples_limit_bytes=limit,
    )
    db.add(run)
    db.flush()
    return CreatedRun(run, reused=False)


def execute_run(
    engine: Engine, settings: Settings, ctx: JobContext, payload: Mapping[str, Any]
) -> None:
    """Worker handler of job kind ``run``: run the model and store the results.

    Raises:
        RuntimeError: If the worker's code or model version differs from the recorded one (the
            run could not be reproduced faithfully).
    """
    run_id = uuid.UUID(str(payload["run_id"]))
    with Session(engine) as db:
        run = db.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"run {run_id} not found")
        version = db.get(ScenarioVersion, (run.scenario_id, run.scenario_version))
        if version is None:
            raise RuntimeError("scenario version not found")
        area = load_study_area(db, run.data_version_id)
        warned = {
            row[0]
            for row in db.execute(
                text("SELECT DISTINCT unit_id FROM data_warnings WHERE data_version_id = :dv"),
                {"dv": run.data_version_id},
            )
        }
        model_id, seed, config, name = run.model_id, run.seed, dict(run.config), version.name
        package_id, package_version = run.package_id, run.package_version
        data_version_id = run.data_version_id
        body = ScenarioBody.model_validate(version.body)
        code_version, model_version = run.code_version, run.model_version
    if code_version != settings.git_commit:
        raise RuntimeError(
            f"this worker runs code {settings.git_commit}, the run was recorded for "
            f"{code_version}; rebuild the worker or start a new run"
        )
    model = get_registry().get(model_id)
    if model.version != model_version:
        raise RuntimeError(f"model {model_id} is {model.version}, run needs {model_version}")
    delay = float(config.get("step_delay_s", 0))

    def progress(fraction: float) -> None:
        ctx.progress(fraction)
        if delay and fraction < 1.0:
            time.sleep(delay)

    model_config = {k: v for k, v in config.items() if k in model.default_config}
    result = model.run(area, body.to_core(str(run_id), name), model_config, seed, progress)

    # Summary statistics come from the samples, at the run's recorded quantile levels (ADR 0017).
    # Runs recorded before ``interval_quantiles`` existed used the model's 5 % / 95 % bounds.
    interval = tuple(config.get("interval_quantiles", DEFAULT_INTERVAL))
    # Statistics are computed from the samples at their stored precision (ADR 0008), so they can
    # be reproduced exactly from the file.
    summaries = summarise_result(as_stored(result, model.sample_dtype), interval)
    samples_path = settings.results_dir / "runs" / str(run_id) / "samples.parquet"
    samples_sha256 = None
    if result.samples:
        samples_sha256 = write_samples(
            result,
            samples_path,
            {
                "run_id": str(run_id),
                "model_id": result.model_id,
                "model_version": result.model_version,
                "package_id": package_id,
                "package_version": package_version,
                "data_version_id": str(data_version_id),
            },
            model.sample_dtype,
        )
    with Session(engine) as db, db.begin():
        rows = [
            {
                "run_id": run_id,
                "unit_id": c.unit,
                "group_id": c.group,
                "service_id": c.service,
                "time_label": c.time,
                "indicator": c.indicator,
                "mean": s.mean if s else None,
                "median": s.median if s else None,
                "low": s.low if s else None,
                "high": s.high if s else None,
                "baseline": c.baseline,
                "edge_effect_warning": c.unit in warned,
            }
            for c, s in ((x.cell, x.summary) for x in summaries)
            if area.unit_roles.get(c.unit) == "core"
        ]
        if rows:
            db.execute(
                text(
                    "INSERT INTO run_results (run_id, unit_id, group_id, service_id, time_label, "
                    "indicator, mean, median, low, high, baseline, edge_effect_warning) VALUES "
                    "(:run_id, :unit_id, :group_id, :service_id, :time_label, :indicator, :mean, "
                    ":median, :low, :high, :baseline, :edge_effect_warning)"
                ),
                rows,
            )
        for table, table_rows in result.tables.items():
            db.execute(
                text(
                    "INSERT INTO run_tables (run_id, table_name, rows) "
                    "VALUES (:run_id, :name, CAST(:rows AS jsonb))"
                ),
                {"run_id": run_id, "name": table, "rows": json.dumps(list(table_rows))},
            )
        stored = db.get(Run, run_id)
        assert stored is not None
        stored.indicators = [
            {
                "id": i.id,
                "label": i.label,
                "unit": i.unit,
                "deterministic": i.deterministic,
                "group_dependent": i.group_dependent,
            }
            for i in result.indicators
        ]
        stored.diagnostics = {**result.diagnostics, "diagnostic_model": model.diagnostic}
        stored.samples_path = str(samples_path) if result.samples else None
        stored.samples_sha256 = samples_sha256
