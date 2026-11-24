# 0010. Privacy rules for request tickets

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: OQ-21, OQ-6, OQ-8; CLAUDE.md "Data and privacy rules"; `core.model.Ticket`

## Context

Tickets are anonymous by design (spatial unit, group, service, timestamps, a yes/no "first request in this period" flag). In small units, the combination of unit, group and timestamps can still identify people (OQ-21). These rules also limit how finely observations can be used for learning (OQ-8, OQ-16). No ticket may be stored before this ADR is accepted.

## Options to evaluate

1. **Minimum cell size (k-anonymity)** for any stored or published aggregate; suppression or merging of small cells.
2. **Timestamp coarsening** (for example to the day or week) at capture time, with exact durations kept only as derived waiting times.
3. **Retention limits**: raw tickets deleted after aggregation into period counts.
4. **Aggregation before storage**: store only counts per `(unit, group, service, period)`.
5. **Differential privacy** for published aggregates.

## Questions to answer before deciding

- What is the minimum cell size, and does it apply to storage, publication or both?
- Which waiting-time indicators (Paper 4 §4.2) survive timestamp coarsening?
- How is the "first request in this period" flag set without storing an identifier (OQ-8)?
- How are people in several groups recorded (OQ-6)?
- How are tickets attributed to facilities, which Paper 4 needs but the ticket fields do not include?
- GDPR assessment (DPIA) for deployments.

## Decision

Not decided.

## Consequences

To be written with the decision.
