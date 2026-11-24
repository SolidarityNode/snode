# 0002. AGPL-3.0 licence

- Status: Accepted
- Date: 2026-11-24
- Related: `LICENSE`, `TRADEMARK.md`, AGENTS.md "Licensing"

## Context

SolidarityNode is public-interest research software for social services. It is likely to be offered as a hosted service (for example by a municipality or a contractor). Improvements made in such deployments should remain available to the public.

## Options

1. **AGPL-3.0**: copyleft that also covers network use; modified hosted versions must publish their source.
2. **GPL-3.0**: copyleft, but hosting a modified version without distributing it does not trigger source release.
3. **Permissive (MIT/Apache-2.0)**: widest reuse, including closed derivatives.

## Decision

License the project under **AGPL-3.0-or-later** (the `LICENSE` file holds the AGPL-3.0 text; package metadata uses the SPDX identifier `AGPL-3.0-or-later`). The project name is not covered by the licence; see `TRADEMARK.md`.

## Consequences

- New dependencies must have AGPL-compatible licences (MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL, GPL-3.0, AGPL-3.0). `scripts/check_licenses.py` and the `licenses` workflow enforce this; each PR states the licence of new dependencies.
- Contributions are accepted under the same licence with a DCO sign-off (no CLA).
- `-or-later` was confirmed by the maintainer (2026-11-24): later versions of the AGPL published by the FSF may also be used.
