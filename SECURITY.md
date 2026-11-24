# Security policy

SolidarityNode is early-stage research software and is **not** ready for production or for processing real personal data.

## Supported versions

Only the `main` branch is supported. There are no releases yet.

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub's [private vulnerability reporting](https://github.com/SolidarityNode/snode/security/advisories/new) ("Security" tab → "Report a vulnerability"). Do not open a public issue.

Include a description, the affected component (core, backend, frontend, containers, CI), steps to reproduce with synthetic data, and the potential impact. We aim to acknowledge reports within 7 days.

## Scope notes

- **Privacy of request tickets** is a security concern. Anything that could re-identify a person from tickets (spatial unit, group and timestamps in small units, OQ-21) should be reported privately.
- Never include real personal data in a report.
- Secrets must never be committed. If you find one in the history, report it privately so it can be rotated.
