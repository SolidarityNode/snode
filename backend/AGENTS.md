# AGENTS.md (backend)

Applies to files under backend/, in addition to the root AGENTS.md. If the two conflict, the root wins; report the conflict.

Explanations and examples: [docs/conventions/backend.md](../docs/conventions/backend.md).

## Rules

- Request handlers never run long computations; they create jobs.
- Runs are immutable and record every reproducibility field: scenario version, data version, code commit, model id and version, seed, configuration.
- Change the database only through Alembic migrations. Never edit a migration that has been merged.
- Check authorisation on every endpoint that reads or writes scenarios, runs, results, users or data packages.
- Tickets and any operational data follow the privacy rules (OQ-21). Never log request bodies that could contain them.
- Settings come from environment variables documented in `.env.example`.
