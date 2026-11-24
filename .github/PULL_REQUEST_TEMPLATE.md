## Summary

<!-- What does this PR change and why? -->

Closes #

## Spec reference

<!-- Paper/section or spec file implemented, and any OQ-n touched. Open OQs must stay open. -->

## Acceptance criteria

<!-- Copy from the issue; tick each one and name the test that covers it. -->

- [ ]

## How to test (UAT)

<!-- MANDATORY. Numbered manual steps a non-developer can follow, each with the expected result.
     Start from a fresh state with `make uat` (see docs/uat/README.md). If a step fails, the
     maintainer comments here and adds the `uat-failed` label. -->

1. Run `make uat` → expected: the URLs are printed and the build commit matches this PR's head.
2. <!-- step --> → expected: <!-- result -->

- [ ] UAT passed by maintainer

## Dependencies and licences

<!-- Every new dependency with its licence (must be AGPL-3.0 compatible). Write "none" if none. -->

| Package | Version | Licence | Why |
| --- | --- | --- | --- |

## Data and privacy

- [ ] No real personal or operational data (synthetic data only, under `core/tests/fixtures/` or `data/synthetic/`)
- [ ] No secrets; `.env.example` updated if configuration changed
- [ ] Ticket/request data stays anonymous (unit, group, service, timestamps only; OQ-21)
- [ ] Third-party data sources attributed in `docs/data-sources.md`

## Checklist

- [ ] `make lint test` passes locally
- [ ] Domain invariants in `AGENTS.md` still hold
- [ ] Public API documented (docstrings cite the spec section)
- [ ] Docs, specs cross-reference and ADRs updated where behaviour or decisions changed
- [ ] Commits follow Conventional Commits and are signed off (`git commit -s`)
