# 0004. BN/DBN library

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: OQ-7, OQ-17, OQ-27; AGENTS.md stack (pgmpy, "evaluate limits via ADR before committing")

## Context

Papers 1–3 need discrete Bayesian networks with expert-elicited CPTs and posterior queries; Paper 2 and Paper 4 need **parameter learning** of CPTs with an expert CPT as prior (OQ-8, OQ-16, OQ-27); Paper 4 needs a **dynamic** BN (OQ-17). Inference runs inside Monte Carlo loops, so speed matters. `core.bayes` defines the interfaces; this ADR picks the engine behind them.

## Options to evaluate

1. **pgmpy** (MIT): Python, discrete BNs, variable elimination and belief propagation, Bayesian parameter estimation with Dirichlet priors, `DynamicBayesianNetwork` class. Check: DBN support is limited to two-slice models and its inference options; performance inside Monte Carlo; maturity of soft evidence.
2. **pomegranate** (MIT): fast, PyTorch-based; check current BN support and API stability.
3. **PyAgrum** (LGPL-3.0 or MIT, verify): mature C++ core, BNs, DBNs (2TBN), learning; check licence terms and packaging.
4. **Own implementation** of the small fixed networks (exact enumeration over few nodes) behind `core.bayes`, possibly with NumPy vectorisation across units.
5. Probabilistic programming (PyMC, NumPyro) for parameter learning only, combined with one of the above for discrete inference.

## Questions to answer before deciding

- Can the engine evaluate the same network for thousands of `(unit, group, service, sample)` cells efficiently, or do we need vectorised custom code?
- Does it support Dirichlet priors with configurable equivalent sample size per row (OQ-27) and learning from incomplete data?
- What DBN structures does it support (OQ-17), and how would we unroll over time?
- Licence compatibility with AGPL-3.0 and long-term maintenance.

## Decision

Not decided.

## Consequences

To be written with the decision.
