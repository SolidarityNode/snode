# 0014. Upward data flow from municipalities to the hub

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: Spec 00 §3 (Deployment), OQ-21, OQ-8, OQ-16, OQ-27; ADR 0010, 0012

## Context

Spec 00 §3 allows municipal installations to share **optional aggregated indicators** upwards to the hub. Tickets are anonymous but can still identify people in small units when combined (OQ-21). Pooled learning across units (OQ-8 take-up, OQ-16 vulnerability relationship, OQ-27 priors) would benefit from data from several municipalities, but only if privacy holds.

## Constraints already stated

- **Only aggregated, anonymised indicators** leave an installation; never tickets or per-request records.
- **Opt-in** per municipality, revocable, and visible to the municipality before anything is sent.
- Aggregation and minimum cell sizes follow the rules decided for OQ-21 (ADR 0010); nothing flows until OQ-21 is decided.

## Options to evaluate

1. **No upward flow** in the first versions.
2. **Manual export** of an aggregate file that the municipality reviews and sends.
3. **Automated push** of aggregates on a schedule, after the municipality opts in.
4. Privacy-enhancing techniques (for example differential-privacy noise on counts) on top of 2 or 3.

## Questions to answer before deciding

- Which indicators are useful to the hub (and to which paper), at which spatial and temporal aggregation?
- Minimum cell size and suppression rules (OQ-21), and how they interact with pooled learning (OQ-8, OQ-27).
- Legal basis and data-protection impact assessment (GDPR); who is controller and processor.
- Audit trail of what was sent and when.

## Decision

Not decided.

## Consequences

To be written. Nothing is sent upwards until this ADR and ADR 0010 are accepted.
