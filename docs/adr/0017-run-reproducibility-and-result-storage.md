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

### Answers for v0.1

- *Fingerprint and reuse*: the input hash below; a match is reused only when its results file
  is present and passes its SHA-256 check (see "Cached reuse").
- *Dirty or unknown code*: refused in production; allowed in development with a visible
  warning (see "Code version").
- *Retention, size, backup*: **no automatic deletion** of samples in v0.1; the size of each
  run's samples file is estimated before it starts (ADR 0008) and the **Admin screen shows the
  results disk usage** (samples files, runs, free space; `GET /storage`). The **database and
  the results volume must be backed up together**, at the same point in time, because run rows
  point to files and record their checksums: a note for the future backup guide (production
  operations ADR, see ADR 0012).
- *Parameter versions*: open until models have CPTs and priors (ADR 0004, OQ-27).
- *Progress and cancellation*: ADR 0006.

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
- **Code version.** With `APP_ENV=production`, backend and worker refuse to start when
  `GIT_COMMIT` is unknown or ends in `-dirty` (settings validation, so `make check-config` fails
  too). In development such runs are allowed and carry a visible warning on the run page
  (`code_version_dirty`): they are reproducible only on the machine that made them. A worker
  built from a different commit (or with another model version) refuses a run queued for
  another one; the run fails with "This run was queued for code …, but the platform now runs
  code … Start the run again." Starting it again records the new code version.
- **Seed and draws.** When a run is started without a seed, one is drawn (`secrets`,
  `[0, 2^31)`) and recorded (`seed_source: drawn`); the number of draws is recorded in the
  configuration (`n_samples`). The screens always send a seed (default 1), and the baseline run
  of an import uses seed 1, so their reuse is unchanged. Python, NumPy and platform versions of
  the worker are recorded on the run and in `metadata.json` (`environment`), **not** in the
  hash.
- **Cached reuse.** Among succeeded runs with the same hash (newest first), the first whose
  samples file is present and passes its SHA-256 check is reused. If none passes, the new run
  records why (`reuse_refused`, shown on the run page) and computes the results again; from
  then on it is the run that is reused.
- **Result summary schema.** Every result value (`run_results`, per unit × group × service ×
  time × indicator) stores its **mean**, its **median** and two **interval quantiles** (`low`,
  `high`). The quantile levels are configurable (`SOLIDARITYNODE_RESULT_INTERVAL_QUANTILES`,
  default `0.05,0.95`, a 90 % interval, `0 < low < 0.5 < high < 1`), recorded in the run
  configuration as `interval_quantiles` and therefore part of the input hash. The statistics are
  computed from the model's samples by `solidaritynode_core.uncertainty.summarise_result` (linear
  interpolation); deterministic values have mean = median = low = high. A non-deterministic
  indicator without samples is refused. The per-sample values stay in Parquet (ADR 0008).
- **diagnostic-v0** was not changed by this summary schema (its version stayed `0.1.0`; it became
  `0.2.0` later for joint draws, ADR 0008): its mean and its
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
- Results: see ADR 0008 (samples are joint draws; the file's SHA-256 is recorded on the run and
  verified on read and export). Comparison is allowed between runs on the same data version (default:
  the baseline run created on import) or between two runs of the same scenario on different data
  versions (labelled); otherwise it is refused. Export: CSV or GeoPackage zipped with
  `metadata.json` holding every reproducibility field.
- The only registered model is `diagnostic-v0`, which is labelled everywhere as "Diagnostic
  model: not a research result".

**Why:** run metadata stays queryable next to scenarios and data versions; files hold the bulk.

## Consequences

- A dirty working tree gives a `-dirty` commit; such runs are reproducible only on that machine
  (development only).
- Parameter versions (CPTs, priors) will join the hash when models have them (ADR 0004, OQ-27).
- The comparison shows a **difference of medians** (labelled so in the UI, the API field
  `difference_of_medians` and its description). There is no comparison export yet; the run
  export has no difference column.
- **Open, to apply with the first research model:** the uncertainty of a difference should
  come from **draw-by-draw differences** when both runs share data version, seed and number of
  draws (common random numbers), as `summarise_total` does for totals; otherwise the screens
  show the two medians and both intervals, labelled, and no interval for the difference.

### Open for later (from UAT, no code now)

- **Hash the scenario's content, not its identity.** The input hash includes the scenario id
  and version, so a duplicated scenario, or a new version that only changes the name or
  description, runs again although its changes are identical. With slow research models,
  consider hashing only the scenario's changes (the overlay body): identical changes would then
  reuse an earlier result, while each run still records which scenario and version asked for
  it (one result, several requesting runs). To decide with the first research model.
- **Retention rule for large installations.** v0.1 deletes nothing automatically. A later rule
  could delete the per-sample Parquet files of old runs while keeping their summary values
  (mean, median, interval) in the database. The ADR must then say what is lost: such runs can
  no longer be exported with samples, re-summarised with other quantiles, compared draw by draw,
  or verified against their SHA-256. They are reproducible only by running them again with the
  recorded code, data, model and seed, not from storage alone.
- **A "New run" button.** Today a new run of unchanged inputs needs a different seed (or the
  API's `force`). A UI button that forces a new run with the same seed would make repeat runs
  explicit, without suggesting that the seed is a setting to tune.
