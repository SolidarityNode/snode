# 0017. Run reproducibility and result storage

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
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

Not decided.

## Consequences

To be written.
