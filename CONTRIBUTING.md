# Contributing to SolidarityNode

Thank you for your interest. SolidarityNode is early-stage research software: code, methodological review, documentation and synthetic test data are all welcome.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues privately as described in [SECURITY.md](SECURITY.md).

## Before you start

Read, in this order:

1. [`CLAUDE.md`](CLAUDE.md): domain invariants, architecture rules and conventions. They apply to every contributor, human or AI.
2. [`docs/specs/README.md`](docs/specs/README.md): how the specification is organised.
3. [`docs/specs/00-domain-model.md`](docs/specs/00-domain-model.md) and [`docs/specs/open-questions.md`](docs/specs/open-questions.md).
4. [`docs/architecture.md`](docs/architecture.md).

## Development setup

Requirements: `git`, `make`, [`uv`](https://docs.astral.sh/uv/), Node.js 26 with [`pnpm`](https://pnpm.io/) 12, and Podman (default) or Docker for the full stack.

```bash
make setup        # install locked dependencies for core, backend and frontend
make lint test    # must pass before every commit
make up           # start db, backend and frontend (Podman by default)
make down
```

With Docker instead of Podman:

```bash
CONTAINER_ENGINE=docker COMPOSE="docker compose" make up
```

`make help` lists all targets. Optional local hooks: `uvx pre-commit install`.

## Workflow

1. **One ticket, one branch, one PR.** Branch name: `feat/<issue-number>-short-name` (or `fix/…`, `docs/…`, `chore/…`).
2. Read the issue fully, including acceptance criteria and the linked spec section.
3. If anything is ambiguous or the spec is silent, **do not invent methodology**: comment on the issue with the question and stop (see below).
4. Implement in small commits and add tests that cover every acceptance criterion. Use synthetic data only.
5. Update docs and the spec cross-reference if behaviour changed.
6. Run `make lint test`, open a PR with the template and reference the issue (`Closes #N`). Do not merge your own PR.

### Commits and DCO sign-off

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`), and sign off every commit:

```bash
git commit -s -m "feat(core): add travel time interface"
```

The sign-off certifies the [Developer Certificate of Origin](https://developercertificate.org/): you wrote the change or have the right to submit it under the project licence (AGPL-3.0). The `dco` CI check rejects PRs with unsigned commits. To fix the last commit: `git commit --amend -s --no-edit`; for several: `git rebase --signoff main`.

### Pull requests

- Fill in every section of the PR template, including the acceptance-criteria checklist, the dependency/licence table and the data/privacy checklist.
- New dependencies must have an AGPL-compatible licence (MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL, GPL-3.0, AGPL-3.0). The `licenses` CI check fails otherwise. State each new dependency's licence in the PR.
- CI runs only the workflows affected by your change (`core`, `backend`, `frontend`, `containers`, `licenses`, plus `dco`).

## Proposing a method

Scientific methods (formulas, CPTs, thresholds, inference schemes) are **specification first, code second**:

1. Open a **Research question** issue (template provided) citing the paper section and the relevant `OQ-n`, if any.
2. Describe the options, their consequences, and references (verify every reference).
3. Once agreed, the decision is recorded in `docs/specs/open-questions.md` (status `decided`, with reasoning and rejected options), the paper changes in `docs/specs/paper-revisions.md`, and the model in `docs/specs/00-domain-model.md`. Technical choices go into an ADR under `docs/adr/`.
4. Only then is an implementation ticket opened, referencing the decision.

## How open questions are handled

- Open questions are listed in `docs/specs/open-questions.md` as `OQ-n` with status `open`, `partly decided` or `decided`.
- **Code never resolves an open question.** Where code touches one, it references `OQ-n` in a docstring and leaves the behaviour undefined (abstract interface or `NotImplementedError`).
- Tickets that depend on an open question carry the `needs-spec` label and wait for the decision.
- If you need a modelling decision to proceed, write an ADR stub (status `Proposed`) or a research question; do not encode the choice silently.

## Data and privacy

- Never commit real personal or operational data. Synthetic data only, under `core/tests/fixtures/` and `data/synthetic/`.
- Request tickets are anonymous by design: spatial unit of origin, social group, service and timestamps only (see OQ-21).
- No secrets in the repository. Use `.env` (gitignored) and keep `.env.example` current.
- Attribute third-party data and record it in [`docs/data-sources.md`](docs/data-sources.md).

## Licence

By contributing you agree that your contributions are licensed under the [AGPL-3.0](LICENSE). The project name is covered by [TRADEMARK.md](TRADEMARK.md), not by the licence.
