# Specifications

The specification is the **source of truth for the science** (CLAUDE.md). If code and spec disagree, stop and flag it; do not silently pick one.

## Files

| File | Role |
| --- | --- |
| [`00-domain-model.md`](00-domain-model.md) | **The current model.** A digest of Papers 1–4: pipeline, notation (OQ-1), entities, the variable catalogue with each variable's kind (input, parameter, computed, evidence, BN node, output) and dimensions, and the module map for `core/`. Where it and a paper disagree, the paper wins and this file is corrected. |
| [`open-questions.md`](open-questions.md) | **Decisions and open questions, with full reasoning.** Every gap or inconsistency found in the papers is an `OQ-n` with status `open`, `partly decided` or `decided`. Decided entries keep the rationale, the rejected options and the spec impact. Code never resolves an open question. |
| [`paper-revisions.md`](paper-revisions.md) | **What must change in the paper texts**, and why, per paper and section. **Update it whenever a decision changes the method**, so the papers and the implementation stay consistent. |
| `NN-name.md` | Per-paper specs, written from the originals: `01-accessibility-capacity.md` (Paper 1), `02-hidden-need.md` (Paper 2), `03-vulnerability.md` (Paper 3), `04-resilience.md` (Paper 4). Not yet written. |
| [`source/`](source/README.md) | The original paper texts, stored **verbatim**. |

## How a paper becomes a spec

1. The original text is stored unchanged in `docs/specs/source/` (see its README).
2. A per-paper spec `docs/specs/NN-name.md` restates the paper section by section in implementable form: definitions, inputs and outputs with units and dimensions, formulas **as decided**, and the paper section each item comes from (for example `Paper 1 §7`). It uses the OQ-1 notation.
3. Every per-paper spec ends with an **"Open questions"** section listing the `OQ-n` that affect it and what remains undefined.
4. When a decision is taken: update `open-questions.md` (status and reasoning), `paper-revisions.md` (text changes), `00-domain-model.md` (model), the per-paper spec, and, if behaviour changes, the code and its docstrings.

## How code refers to the spec

- Every public type and function in `core` cites its source (for example `Paper 3 §15`, or `Spec 00 §4.4` where no paper section exists) in its docstring.
- Where code touches an open question, the docstring names it (`OQ-n`) and the behaviour stays undefined (an abstract interface or `NotImplementedError`).
- The variable catalogue in `core/src/solidaritynode_core/model/catalogue.py` mirrors Spec 00 §4; tests check that BN nodes, computed variables and scenario parameters stay distinct.
- Technical decisions go to ADRs in [`docs/adr/`](../adr/README.md).
