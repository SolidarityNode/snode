# Backend conventions

Rules: [`backend/AGENTS.md`](../../backend/AGENTS.md). The root [`AGENTS.md`](../../AGENTS.md) also applies.

## Request handlers create jobs

Request handlers never run long computations; they create jobs (ADR 0006).

**Why:** simulations can take minutes; a blocked handler times out and holds a worker.

**Example (illustrative; the runs endpoints do not exist yet):** `POST /runs` validates the scenario, enqueues the run and returns `202` with the run id; the client polls the run status.

## Runs are immutable and reproducible

Record every reproducibility field: scenario version, data version, code commit, model id and version, seed, configuration (Spec 00 §3, ADR 0017).

**Why:** a result is only useful as evidence if the same inputs reproduce it.

## Database changes through Alembic only

Change the schema only through Alembic migrations, and never edit a migration that has been merged; add a new one instead.

**Why:** installations that already applied a merged migration would silently diverge.

## Authorisation on every endpoint

Check authorisation on every endpoint that reads or writes scenarios, runs, results, users or data packages.

**Why:** scenarios have owners and visibility, and installations hold municipal data (ADR 0015 decides the mechanism).

## Privacy of tickets and operational data

Tickets and other operational data follow the privacy rules (OQ-21, ADR 0010). Never log request bodies that could contain them.

**Why:** logs are copied, shipped and kept longer than the database; a logged body defeats anonymity by design.

## Settings from the environment

Settings come from environment variables documented in `.env.example` (see "Configuration" in `CONTRIBUTING.md`).

**Why:** development must run with no manual editing of `.env`, and production values are never committed.
