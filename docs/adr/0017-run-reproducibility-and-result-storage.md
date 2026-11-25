# 0017. Run reproducibility and result storage

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
- Related: Spec 00 §3 (Run, Result), AGENTS.md invariant 6 (uncertainty); ADR 0006, 0008, 0013, 0016

## Context

Spec 00 §3: a **run** is one **immutable** execution of a scenario and records everything needed to reproduce it: scenario version, data package version, code version (git commit), model and parameter version (CPTs, priors), random seed, configuration. Lifecycle `queued → running → succeeded | failed | cancelled`, with progress. Identical inputs may reuse results. A **result** belongs to one run: summary values per `unit × group × service` (probabilities, intervals) in the database for maps; full Monte Carlo samples in Parquet files. Randomness goes through an explicit seed (AGENTS.md). `/version` already reports the git commit of the running build.

## Options to evaluate

1. **Run record in PostgreSQL** (inputs as foreign keys and hashes, lifecycle, progress) plus **Parquet files** per run in a content-addressed store; the database indexes them (ADR 0008).
2. Experiment-tracking tool (for example MLflow, Apache-2.0) for run metadata and artefacts.
3. Files only (run directory with `run.json` and Parquet), indexed by the database later.

## Questions to answer before deciding

- Exact fingerprint of a run (which inputs are hashed) and when results may be reused.
- How the code version is pinned when the working tree is dirty (refuse to run outside development?).
- Retention and deletion of samples; size limits; backup.
- Model and parameter versioning for CPTs and priors (with ADR 0004, OQ-27).
- How background jobs report progress and cancellation (ADR 0006).

## Decision

**Accepted for v0.1, to be revisited: option 1, run record in PostgreSQL plus Parquet files.**

- A run is immutable and records: scenario id and version, data package id and version (and the
  data version row), code version (`GIT_COMMIT` of the build), model id and version (from the core
  model registry), random seed and configuration. Lifecycle, progress and error live in its job
  (ADR 0006).
- **Input hash**: SHA-256 of the canonical JSON of scenario id, version and body, package id,
  version and manifest checksum, code version, model id and version, seed and configuration (no
  timestamps). Starting a run whose hash matches a **succeeded** run returns that run unless the
  user forces a rerun; failed or cancelled runs are never reused.
- A worker built from a different commit refuses a run recorded for another code version (the run
  fails with a clear message), so results always come from the recorded code.
- **Result summary schema.** Every result value (`run_results`, per unit × group × service ×
  time × indicator) stores its **mean**, its **median** and two **interval quantiles** (`low`,
  `high`). The quantile levels are configurable (`SOLIDARITYNODE_RESULT_INTERVAL_QUANTILES`,
  default `0.05,0.95`, a 90 % interval, `0 < low < 0.5 < high < 1`), recorded in the run
  configuration as `interval_quantiles` and therefore part of the input hash. The statistics are
  computed from the model's samples by `solidaritynode_core.uncertainty.summarise_result` (linear
  interpolation); deterministic values have mean = median = low = high. A non-deterministic
  indicator without samples is refused. The per-sample values stay in Parquet (ADR 0008).
- **diagnostic-v0** is unchanged (same outputs, so its version stays `0.1.0`): its mean and its
  own 5 %/95 % bounds equal the stored mean and default quantiles, and the median is computed
  from its existing samples (core test `test_diagnostic_summary_matches_its_samples_…`).
- **Totals** across units or groups are computed from the stored samples, draw by draw
  (`summarise_total`: draw *i* of the total is the sum of draw *i* of each part), then
  summarised. Medians and interval bounds are never added. No screen shows totals yet; any that
  is added must use this.
- Comparison differences are differences of **medians**; the two intervals are shown next to
  them, not combined.
- Export: CSV and GeoPackage columns `median`, `low`, `high`, `mean`; `metadata.json` states the
  quantile levels and what each column is.
- Runs stored before migration 0005: `value` became `mean`; deterministic rows got `median =
  mean`; sampled rows have no median ("not available") and no recorded levels, because runs are
  immutable and their samples are not re-read. Start such a run again to get them.
- Results: see ADR 0008. Comparison is allowed between runs on the same data version (default:
  the baseline run created on import) or between two runs of the same scenario on different data
  versions (labelled); otherwise it is refused. Export: CSV or GeoPackage zipped with
  `metadata.json` holding every reproducibility field.
- The only registered model is `diagnostic-v0`, which is labelled everywhere as "Diagnostic
  model: not a research result".

**Why:** run metadata stays queryable next to scenarios and data versions; files hold the bulk.

## Consequences

- A dirty working tree gives a `-dirty` commit; such runs are reproducible only on that machine.
- Parameter versions (CPTs, priors) will join the hash when models have them (ADR 0004, OQ-27).
