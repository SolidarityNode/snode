# 0005. Inference approach, CPT size and discretisation

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: OQ-7, OQ-11, OQ-15, OQ-4

## Context

Continuous quantities (service gap ratio, Group Exposure, Service Loss, need-based gap, access deterrence) enter discrete BNs. Thresholds for Group Exposure and Service Loss are open (OQ-15); the relation between the deterministic Service Gap and its BN node is open (OQ-4). The non-take-up node has four three-state parents, giving 81 CPT rows (OQ-11), which is hard to elicit.

## Options to evaluate

1. **Fixed thresholds** per variable, documented in configuration (simple; sensitive to the cut points).
2. **Soft/virtual evidence** from the continuous value (likelihoods over states) instead of hard discretisation.
3. **Quantile-based** thresholds from the baseline distribution (data-driven; not comparable across areas).
4. For large CPTs: **intermediate nodes** (for example combining access deterrence and outside alternatives), **ranked nodes** or other parametric elicitation (Fenton et al.; verify reference), or noisy-OR/MAX style models.
5. Exact inference (enumeration / variable elimination) vs sampling; with networks this small, exact is likely feasible.

## Questions to answer before deciding

- Which variables are discretised, with which states and thresholds, and who sets them (experts, data)?
- Hard vs soft evidence, and how this interacts with Monte Carlo (sample, then discretise?).
- How are implausible parent combinations flagged or skipped during elicitation (OQ-11)?
- Elicitation protocol: frequency format, number of experts, aggregation.

## Decision

Not decided.

## Consequences

To be written with the decision.
