# Open questions

> Issues found while turning Papers 1–4 into a model. **None of these may be resolved in code.** Implementation tickets that depend on one are labelled `needs-spec`. Each question becomes a `research-question` or `adr` issue. Reference them in code and docs as `OQ-n`.
>
> Status values: `open`, `decided` (with link to ADR or spec update).

## Summary

| OQ | Topic | Status |
| --- | --- | --- |
| OQ-1 | indices, §5–8 | decided (2026-11-23) |
| OQ-2 | capacity allocation, §7 | decided (2026-11-23) |
| OQ-3 | access weight, §5 | open |
| OQ-4 | service gap vs BBN, §8–9 | open |
| OQ-5 | modes, §3.4–5 | open |
| OQ-6 | groups, §4 | open |
| OQ-7 | BN engine and discretisation, §9–10 | open |
| OQ-8 | from probability to quantity, §12 | decided (2026-11-23) |
| OQ-9 | susceptibility index, §6–7 vs Paper 3 §12 | decided (2026-11-23) |
| OQ-10 | possible double counting, §4, §10 and Paper 3 | decided (2026-11-23) |
| OQ-11 | diagram vs formula, §8 vs §10 | decided (2026-11-23) |
| OQ-12 | baseline gap inside service loss, §14–15 | decided (2026-11-23) |
| OQ-13 | affected population, §11 | open |
| OQ-14 | disrupted service function, §13 | open |
| OQ-15 | vulnerability states and thresholds, §17, §21 | partly decided (2026-11-23) |
| OQ-16 | definition of vulnerability, Paper 3 §2, §17 vs Paper 4 §2.1, §10 | decided (2026-11-23) |
| OQ-17 | DBN structure, §5, §12 | open |
| OQ-18 | observed consequence, §9 | open |
| OQ-19 | resilience estimation, §13 | open |
| OQ-20 | resource mobilisation, §6 | open |
| OQ-21 | re-identification risk, §4.1 | open |
| OQ-22 | terminology | open |
| OQ-23 | Digital Twin wording | open |
| OQ-24 | unit of need and depth of loss | decided (2026-11-23) |
| OQ-25 | reference period | open |
| OQ-26 | delay versus loss | approach decided (2026-11-23), values open |
| OQ-27 | weight of expert priors against observed data | open |

Future-work notes (`N-…`): N-2a 3SFCA, N-2b constrained allocation for sensitivity, N-2c constrained allocation in Paper 4, N-8a intensity of hidden need, N-8b small area estimation, N-8c direct validation of hidden need, N-24a severity weighting, N-24b breadth as BN parent.

## Paper 1 (accessibility, capacity, service gap)

**OQ-1 (indices, §5–8).** `T_ij` uses `i` as origin and `j` as facility, but demand and supply (`D_j^g`, `Supply_j^g`) are indexed by `j`, as if `j` were the demand location. Paper 3 also reuses `s` for scenario. Define one consistent notation. **Status: decided (2026-11-23).**

- **Indices:** `i` spatial unit, `f` facility, `g` population group, `s` service, `m` transport mode, `c` scenario, `t` time, `l` state of a discrete variable (for example in `Σ_l P(X = l) …`).
- **Placement:** demand, supply and gap belong to the spatial unit `i`; travel time is `T_if^{g,m}`.
- **Symbols fixed by other decisions:** `k` intensity (service units per person per period, OQ-24); `p` need prevalence and `τ` take-up (OQ-8); `P(·)` probability. "k-anonymity" is used only as a term in text, never as a symbol.
- **Rationale.** Removes the `i`/`j` inconsistency of Paper 1 and the double use of `s` in Paper 3, and avoids collisions created by later decisions (`k` as intensity and as state index).

**OQ-2 (capacity allocation, §7).** `C_ij^effective = C_i^functional × w(T_ij)` and `Supply_j^g = Σ_i C_ij^effective`. A facility's full capacity is counted for every origin, so supply can exceed what the facility can deliver when several areas compete for it. The text does not give an allocation or competition mechanism. **Status: decided (2026-11-23).**

- **Decision.** Use a two-step floating catchment area (2SFCA) allocation. Each facility's functional capacity is shared among the spatial units (and groups) that can reach it, in proportion to their access-weighted demand. Groups compete for the same facility capacity. The shares a facility gives out sum to its capacity.
- **Rationale.**
  1. Removes the over-counting of supply in the original formula, so the Service Gap is not systematically underestimated.
  2. Does not redistribute demand to alternative facilities after a capacity loss. This matches Paper 3, which explicitly excludes adaptive redistribution and alternative activation (reserved for Paper 4).
  3. Makes no assumption about how people choose facilities beyond the access weight `w(T)`.
  4. Cheap enough to run inside Monte Carlo and easy to explain.
- **Known limitations.**
  - Demand inflation: a unit inside several catchments has its full demand counted in each one.
  - A unit can be allocated more supply than its demand while surplus capacity could cover another unit.
- **Notes for future work** (tracked as `research-question` issues, not implemented now):
  - **N-2a: 3SFCA.** Evaluate a three-step floating catchment area variant (for example Wan, Zou & Sternberg, 2012) that splits each unit's demand among facilities with selection probabilities to correct demand inflation. Compare against 2SFCA on synthetic and real data. Verify references before use.
  - **N-2b: Constrained allocation (option C) for sensitivity analysis.** Implement a capacity-constrained allocation (linear programming or capacity-constrained gravity model) with flows bounded by facility capacity and by unit demand. Use it only as an alternative model in sensitivity analysis ("how much would the Service Gap change under coordinated allocation?"), never as the baseline. It assumes a behaviour rule and perfect coordination, which understates the real gap, and it redistributes demand after disruptions, which Paper 3 excludes.
  - **N-2c: Paper 4.** Constrained allocation is a natural candidate for modelling redistribution and resource mobilisation in Paper 4, where redistribution is part of the resilience mechanism.
- **Spec impact.** Paper 1 §7 formulas for effective capacity and supply must be rewritten to the 2SFCA form. The access weight `w(T)` remains open (OQ-3).

**OQ-3 (access weight, §5).** Functional form and parameters of `w(T)` (decay, cut-offs), and whether they differ by group and mode, are not specified. Status: open.

**OQ-4 (service gap vs BBN, §8–9).** Service Gap is defined by a deterministic formula, then discretised, and also appears as a BBN node. It is unclear whether the BBN reproduces the formula, refines it, or models something beyond it, and how thresholds, CPTs and Monte Carlo interact. Status: open.

**OQ-5 (modes, §3.4–5).** Accessibility is computed per mode, but supply and gap are per group. How modes combine for a group (mode shares, best mode, weighting) is not specified. Status: open.

**OQ-6 (groups, §4).** Group definitions and thresholds, demand rates and their sources are not fixed. Groups can overlap (for example an elderly person with low income), so summing groups may double count population and demand. Overlap handling is not specified. **Also (added 2026-11-23):** tickets record a social group; decide whether a ticket can carry several groups or a priority rule applies, consistently with how population and demand handle overlap. Status: open.

**OQ-7 (BN engine and discretisation, §9–10).** Discretisation of continuous inputs, CPT size for nodes with many parents, the elicitation protocol and the choice of inference engine are open. Decide through ADRs. Status: open.

## Paper 2 (hidden need)

**OQ-8 (from probability to quantity, §12).** `P(HN = Low/Medium/High)` must become `ExpectedHiddenNeed` in the same units as demand to compute `ETN = EstimatedDemand + ExpectedHiddenNeed`. The conversion is not defined. **Status: decided (2026-11-23).**

- **Goal stated by the author.** The method must support statements of the form "X % of the group has need that is not visible", so hidden need is measured in **people of the group**, not as a share of estimated demand. (Rejected: hidden need as a share of estimated demand, because a group that barely appears in services would then also show almost no hidden need, which may be exactly where hidden need is largest.)
- **Decision ("need prevalence × non-take-up").**
  1. `p_{i,g,s}`: **need prevalence**, the share of the group that needs the service in the reference period.
  2. `τ_{i,g,s}`: **take-up**, the share of people with need who **express** it, that is make a request, **whether or not they are then served**. `1 − τ` is **non-take-up**: people with need who never make a request because they do not seek the service, cannot access it, are discouraged by cost, distance or expected waiting, or use alternatives (Paper 2 §1.1).
  - **Separation of concepts (decided 2026-11-23):** **hidden need** is need that is never expressed (Paper 2). **Unmet expressed need** (requests not fulfilled within the maximum acceptable waiting time, or expired) belongs to Service Gap (Paper 1) and Service Loss (Paper 3). Defining `τ` as "served" instead would make capacity shortages look like low take-up and count the same unmet need twice.
  3. Visible need (people) `= Population × p × τ`. **Hidden need (people) `= Population × p × (1 − τ)`**. **Share of the group with hidden need `= p × (1 − τ)`**. Total need (people) `= Population × p`.
  4. The Paper 2 BN has four parents: Social Susceptibility, need-based gap (OQ-10), access deterrence and alternatives outside the network (OQ-11). Its target node is interpreted as the **level of non-take-up**, with states defined as ranges of `1 − τ` (for example Low 0–20 %, Medium 20–50 %, High 50–80 %; exact bounds to be set with experts).
  5. Expected non-take-up is `Σ P(state) × value`, with values sampled within each range in Monte Carlo (not fixed midpoints), so results are reported with an interval, for example "7–17 % of the group (90 % interval) has hidden need".
  6. In service units (OQ-24): `ETN = Population × p × k`; hidden need in units `= Population × p × (1 − τ) × k`.
- **Source of `p`.** To be determined during the work: survey or administrative data if available (candidates to check: EU-SILC, EHIS, SHARE for older people; usually national or regional, not per ΤΚ), otherwise expert elicitation. `p` is an uncertain parameter, configured per group, service and, where data allow, area. Not hard-coded.
- **Meaning of Paper 1 demand.** Paper 1's `DemandRate` is **visible use under average conditions** (typically a national or regional rate), not need prevalence. If a source gives prevalence, it feeds `p`. This must be stated explicitly in Paper 1 §6.
- **Use of observations (revised 2026-11-23; replaces an earlier consistency check).**
  - *Rejected:* requiring "visible need `Population × p × τ` ≈ Paper 1 estimated demand". Paper 1 demand applies an average rate and is not a local observation, so local differences are exactly what the method should reveal; and enforcing equality would fix `τ = D / (Population × p)` arithmetically, leaving the BN nothing to estimate.
  - *Decided:*
    1. **Aggregate calibration** where aggregate administrative figures exist (for example people served in the whole municipality): the sum of visible need over all units should be close to them; local differences are allowed.
    2. **Observed use as evidence**: local administrative records now, tickets later (Paper 4), enter the BN as observations and update take-up by Bayesian **parameter learning** of `P(non-take-up | parents)`, pooling information across units with similar characteristics. Same mechanism as OQ-16; weight of experts against data per OQ-27. Updating per cell (unit × group × service × period) is avoided because counts are small and privacy rules (OQ-21) restrict them.
    3. Paper 1 demand is kept only as a **descriptive indicator**: the ratio of visible need to `D` shows where local use departs from the average.
  - *Identifiability (limitation to state in Paper 2):* use data observe only the product `p × τ × k` (how many requests), not need and take-up separately. Hidden-need estimates therefore rest on independent information about `p` (surveys or experts). Mandatory sensitivity analysis of hidden need with respect to `p`.
  - *Persons versus requests:* anonymous tickets count requests, not people. A ticket field "first request in this period" (yes/no, no identifier) allows counting people without identifying them, which separates `k` from `p × τ`.
  - *Completeness of recording:* if some facilities or channels (phone, walk-in) are not recorded, observed use is too low, `τ` is underestimated and hidden need overestimated. Recording coverage is tracked per facility and period, and updating uses only data from facilities with full or known coverage.
  - *Change over time:* take-up changes when services change; learning the CPT parameters (not a fixed `τ` per unit) lets `τ` follow changes in its parents.
- **Rationale.**
  1. Answers the author's question directly and bounds hidden need by the population automatically.
  2. Splits two different questions (how many need, how many do not reach the service), each easier for experts ("out of 100 older people who need care, in an area with low accessibility and few alternatives, how many do not receive it?") and each validated separately.
  3. Builds on the established non-take-up literature and on possible survey data for prevalence.
  4. Links to Paper 4: tickets count people who reach services, informing `τ` once `p` is known.
  5. Simplifies OQ-10: total need is `Population × p`; the BN only splits it into visible and hidden.
  6. Easy to implement: array multiplications plus the discrete BN already required.
- **Notes for future work** (tracked as `research-question` issues):
  - **N-8a: Intensity of hidden need.** People with hidden need may need more service units than visible users (for example because need accumulates). Initially the same `k` is used for both; revisit with data.
  - **N-8b: Small area estimation.** If regional survey data on unmet need become available, downscale them to spatial units with small area estimation methods using unit covariates, as an independent validation of the Paper 2 BN.
  - **N-8c: Direct validation of hidden need.** Tickets never show hidden need, by definition. Plan a validation study with direct measurement: outreach in a sample of units (home visits or telephone survey counting people with need who never requested help) and referrals from other actors (doctors, social workers, parishes) of people unknown to the services.
- **Spec impact.** Paper 2 §1.1, §2, §10, §12, §17, §19.2 (non-take-up interpretation, people-based outputs, interval reporting), Paper 1 §6 (meaning of `DemandRate`), Paper 3 §5 (`ETN` definition).

**OQ-9 (susceptibility index, §6–7 vs Paper 3 §12).** Paper 2 writes `SS_{i,g}`, Paper 3 writes `SS_g`. Is susceptibility group-level or unit-and-group-level? **Status: decided (2026-11-23).**

- **Decision:** `SS_{i,g,s}`, per spatial unit, group **and service**.
- **Rationale.** Indicators such as living alone or household composition vary spatially, and a group is not equally prone to unmet provision for every service (for example older people living alone are highly susceptible for home care, much less for employment services).
- **Consequences.**
  1. Indicators, or their weighting, may differ by service; experts define them per group and service. The rule of Paper 2 §7 still applies: an indicator used to define the group is never reused as susceptibility evidence.
  2. More elicitation effort than a single susceptibility per group; to be organised in the elicitation protocol (with OQ-7).
  3. Unit-level indicators may be unavailable at fine resolution or based on very small counts; their uncertainty enters Monte Carlo, and small area estimation may be needed (see N-8b).
  4. Susceptibility still never depends on the service system (availability, accessibility, capacity), as Paper 2 §6.2 requires; spatial variation comes only from social characteristics.
- **Spec impact.** Paper 2 §6–7 and Paper 3 §12, §17 (write `SS_{i,g,s}`).

**OQ-10 (possible double counting, §4, §10 and Paper 3).** Hidden Need is conditioned on Service Gap, which is derived from estimated demand; `ETN` then adds hidden need to demand, and Paper 3 uses `ETN` to compute Service Loss. Verify that information is not counted twice (Paper 3 already flags this for Need Pressure). **Status: decided (2026-11-23).**

- **Original problem resolved by OQ-8.** Total need is `Population × p × k` and no longer contains Paper 1 estimated demand, so demand is no longer counted both directly in `ETN` and indirectly through Service Gap.
- **Remaining problem found: a loop.** Paper 1 Service Gap is computed from estimated demand, which reflects visible use (`p × τ`). Using it as a parent of non-take-up means that a group with low take-up shows low demand, hence a small gap, hence the BN infers low non-take-up: the group with the most hidden need would appear to have the least.
- **Decision ("option A").** The parent of non-take-up in Paper 2 is a **need-based gap**: `max(0, Population × p × k − Supply)`, the shortfall of supply (2SFCA, OQ-2) relative to **total need**, not relative to current users. It does not depend on `τ`, so the loop is broken. Paper 1's demand-based Service Gap is unchanged and keeps answering Paper 1's question.
- **Rationale.** People are discouraged by full facilities and long waits relative to everyone who needs the service, not relative to those already using it.
- **Rejected.** Supply per inhabitant as parent (ignores how many need the service); keeping Paper 1 Service Gap with sensitivity checks (leaves the loop in place).
- **Spec impact.** Paper 2 §9.2 ("Service Gap from Paper 1, not recomputed") must be rewritten: Paper 2 reuses Paper 1 supply but compares it with total need.

**OQ-11 (diagram vs formula, §8 vs §10).** The Paper 2 diagram shows Social Susceptibility feeding Service Gap and Accessibility, while §10 gives `P(HN | SS, SG, A, ALT)` with all four as parents of Hidden Need, and §6 states susceptibility is independent of service gap and accessibility. Fix the edge set. **Status: decided (2026-11-23).**

- **Edge set.** Four parents of the non-take-up node, no edges between them: Social Susceptibility, need-based gap (OQ-10), access deterrence, alternatives outside the network. The §8 diagram, where susceptibility feeds Service Gap and Accessibility, is corrected, since §6.2 defines susceptibility as independent of the service system.
- **Problem found.** The need-based gap uses 2SFCA supply, which already includes accessibility (through `w(T)`) and all reachable facilities. With accessibility and alternatives defined as in Paper 2 §9.3–9.4 (travel time, number and capacity of alternative facilities), the same information would enter twice. The three parents would also be derived from the same facilities and network, so experts would be asked about combinations that hardly occur.
- **Decision ("option A"): non-overlapping definitions.**
  1. **Need-based gap**: how adequate the facility network is for everyone who needs the service. Already includes access and alternative facilities.
  2. **Access deterrence**: accessibility only as a **direct deterrent to seeking** the service (for example travel time to the nearest facility offering it), a different mechanism from how much capacity reaches the unit.
  3. **Alternatives outside the network**: only options **not** among the modelled facilities (private services, family, NGOs, parishes), matching Paper 2 §1.1 ("use alternative solutions"). Where no data exist, start from expert estimates.
- **Rejected.** Keeping only susceptibility and the need-based gap: simpler (9 combinations) but loses the "too far to ask" and "covered elsewhere" mechanisms.
- **Still to address (with OQ-7).** Four three-state parents give 81 CPT rows. Candidate techniques: intermediate nodes (for example combining access deterrence and outside alternatives) or parametric elicitation such as ranked nodes (Fenton et al.; verify reference). Elicitation should skip or flag implausible combinations.
- **Spec impact.** Paper 2 §8 (diagram), §9.3–9.4 (definitions of accessibility and alternatives), §10.

## Paper 3 (disruption, vulnerability)

**OQ-12 (baseline gap inside service loss, §14–15).** `PUN = max(0, ETN − AvailableService^D)` and `SL = PUN / ETN`. Because baseline supply may already be below `ETN`, `SL` mixes the baseline gap with disruption-induced loss. Should loss be measured relative to baseline available service? **Status: decided (2026-11-23).**

- **Definitions.** For unit `i`, group `g`, service `s`, scenario `c`:
  - `AS⁰`: available service without disruption (baseline); `ASᴰ`: available service under the scenario.
  - `PUN⁰ = max(0, ETN − AS⁰)`: **baseline gap**, need already unmet before any disruption.
  - `PUNᴰ = max(0, ETN − ASᴰ)`: unmet need under the scenario.
- **Decision.**
  1. **Disruption loss** is the counterfactual difference `ΔPUN = PUNᴰ − PUN⁰` (equivalently, covered need without disruption minus covered need with it). It is always computed and stored in absolute units (see OQ-24).
  2. **Service Loss (BN evidence)** is `SL = (PUNᴰ − PUN⁰) / ETN` ("option A"), in `[0, 1]`, equal to 0 when nothing changes.
  3. **Baseline gap** stays outside Service Loss. Its effect is examined through Need Pressure in sensitivity analysis, as Paper 3 §6 already specifies. It becomes an additional BN parent only if sensitivity shows it adds independent information, and only through an ADR.
  4. **Relative Service Loss** `SL′ = (PUNᴰ − PUN⁰) / min(ETN, AS⁰)` ("option A′", share of the service the group was receiving that is lost) is computed and stored as a secondary indicator for maps and sensitivity analysis. It is **not** a BN node.
- **Rationale.**
  1. Each parent of Vulnerability measures only its own aspect: Group Exposure (how much of the group is affected), Service Loss (how much service the event removes), Social Susceptibility (how prone the group is). The pre-existing condition of the group belongs to susceptibility or Need Pressure, not to the loss.
  2. Passes the logical check that a zero-severity scenario gives zero loss. With the paper's formula the baseline gap would leak into Vulnerability, contradicting Paper 3 §6, which excludes Need Pressure as a parent to avoid double counting.
  3. Consistent with Paper 4: loss is measured against pre-event performance (as in the resilience literature, for example Bruneau et al., 2003), so `ServiceLoss(t)` starts at 0 and returns to 0 on full recovery.
  4. Normalising by `ETN` keeps the paper's wording ("share of estimated need"), matches the logic of Group Exposure (share of the group), and is stable for small values.
- **Known limitation.** `SL` understates the consequence for groups that already had very little coverage (for example `AS⁰` 100 → 0 with `ETN` 800 gives `SL = 0.125` while `SL′ = 1.0`). This is why `SL′` is kept as a secondary indicator.
- **Expert elicitation note.** Experts filling the Vulnerability CPT must be told that "Service Loss High" means "the disruption left a large additional share of the group's total need uncovered", not "the group lost most of what it was receiving".
- **Spec impact.** Paper 3 §14–15 and §28 must be rewritten with these definitions.

**OQ-13 (affected population, §11).** How `AffectedPopulation` is derived from dependency and accessibility (Paper 1), disrupted facilities and the disrupted network is described only in outline. Catchment and dependency rules are not specified. Status: open.

**OQ-14 (disrupted service function, §13).** `AvailableService^D = f(Capacity^D, Accessibility^D)` is unspecified. Is it the Paper 1 supply formula with disrupted inputs? Status: open.

**OQ-15 (vulnerability states and thresholds, §17, §21).** The network uses Low / Medium / High, while the elicitation table contains "Very High". Discretisation thresholds for Group Exposure and Service Loss are not given. **Status: partly decided (2026-11-23).**

- **Decided:** Vulnerability has three states, Low / Medium / High. "Very High" is removed from the elicitation table of Paper 3 §21.
- **Open:** discretisation thresholds for Group Exposure and Service Loss (with OQ-7).

**OQ-24 (unit of need and depth of loss; raised while deciding OQ-12).** In what unit are need, capacity and loss measured, and how is the depth of loss per person described? **Status: decided (2026-11-23).**

- **Decision: unit of need ("people × intensity").**
  1. Need is described by two quantities: the number of people with need `N_{i,g,s}` in the reference period, and the intensity `k_{g,s}`, the service units one person needs in that period (visits, appointments or hours, defined per service).
  2. Need in service units is `N × k`. Capacity, 2SFCA allocation, Service Gap, unmet need and Service Loss are computed in **service units**. People are recovered when needed.
  3. Each service has its own unit. Quantities of **different services are never summed**, consistent with the unit of analysis, which includes the service.
  4. `k_{g,s}` is an uncertain parameter sampled in Monte Carlo, like the demand rate. People with need are `N = Population × p` (OQ-8); Paper 1's demand rate is visible use, not need prevalence (corrected by OQ-8).
  5. Severity weighting across services is **not** applied now (see N-24a).
- **Decision: depth of loss ("option B").**
  1. The BN keeps Service Loss in service units (OQ-12); depth per person is not a BN parent.
  2. How shortage is spread among people (**rationing**) is a scenario parameter with two bounding cases: **uniform** (everyone receives proportionally less) and **concentrated** (some are fully served, others not at all).
  3. Secondary indicators are computed and stored for both cases, following the Foster–Greer–Thorbecke family of poverty measures (Foster, Greer & Thorbecke, 1984; verify reference): **breadth** (share of people who lose any service), **depth** (mean loss of those affected) and **severity** (loss weighted towards those who lose most, for example squared per-person loss).
  4. Results report how conclusions change between the two rationing cases.
  5. In Paper 4 the actual rationing pattern is estimated from tickets (fulfilled, overdue, expired requests per person).
- **Rationale.** Capacity data (places, staff, throughput) is naturally in service units, and intensity differs strongly between groups (for example several visits a month for the elderly against one for the unemployed), so counting only people would hide real differences. Counting only units would hide how many people are affected. Rationing is unknown without operational data, so it is bounded by scenarios rather than assumed.
- **Notes for future work** (tracked as `research-question` issues):
  - **N-24a: Severity weighting.** Weight service units by criticality or time-sensitivity (for example medical against administrative). Candidate for Paper 4, where resource types already appear. Weights require expert justification.
  - **N-24b: Breadth as BN parent ("option C").** Consider breadth as an extra parent of Vulnerability only if sensitivity analysis shows it matters. It enlarges the expert table and correlates with Group Exposure.
- **Spec impact.** Paper 1 §6–8 (demand, capacity and gap expressed in service units with `N` and `k`), Paper 2 §12 (hidden need in the same units), Paper 3 §13–15 (loss in units, rationing scenarios, secondary indicators), Paper 4 §4.2, §9 (observed rationing from tickets).

**OQ-25 (reference period).** Need and capacity must be measured over the same period (for example week or month). The choice also relates to the DBN time step in Paper 4 (OQ-17). Status: open.

**OQ-26 (delay versus loss).** When does a late service count as lost? **Status: approach decided (2026-11-23), values open.**

- **Decision.** Each service has a **maximum acceptable waiting time**. A request not fulfilled within it counts as unmet need. This matches the overdue and expired request indicators of Paper 4 §4.2.
- **Open.** The threshold value per service, and whether it differs by group. To be set with domain experts and recorded per service in configuration, not in code.

## Paper 3 and Paper 4

**OQ-16 (definition of vulnerability, Paper 3 §2, §17 vs Paper 4 §2.1, §10).** Paper 3 infers `V_{i,g,sc}` (original notation) per scenario from exposure, service loss and susceptibility. Paper 4 defines vulnerability as a baseline predisposition from demographic and socioeconomic factors and baseline accessibility and capacity, independent of a scenario, and updates it from observations. Reconcile: is vulnerability per scenario, a baseline, or both? **Status: decided (2026-11-23).**

- **Problem found.** In Paper 4, Expected Consequence combines Vulnerability with the functional state of the system. If Vulnerability is Paper 3's (which already contains the disruption through Group Exposure and Service Loss), the disruption is counted twice. If it is Paper 4's baseline predisposition, it largely duplicates Social Susceptibility (Paper 2) plus the baseline system (Paper 1).
- **Decision ("option D"): vulnerability is the relationship, not a number.**
  1. The vulnerability of a group is **how a disruption is turned into consequences for that group**, given its Social Susceptibility. In the BN it is the conditional relationship `P(V | GE, SL, SS)`, that is the CPT of the Vulnerability node, by analogy with vulnerability or fragility curves in seismic engineering (damage as a function of intensity, not the damage of one event; verify literature, for example the HAZUS methodology, before citing).
  2. **Paper 3** builds the relationship (CPT initialised by expert elicitation) and **evaluates it at scenarios**. `V_{i,g,s,c}` means "vulnerability evaluated at scenario `c`". Paper 3 §2 is kept, with wording adjusted to say that the scenario value is an evaluation of the group's vulnerability relationship.
  3. **Paper 4** evaluates the same relationship at **observed** disruptions: tickets give the functional state, from which observed `GE(t)` and `SL(t)` are derived, and the relationship gives the Expected Consequence. The disruption enters **once**, through `GE` and `SL`, so there is no double counting.
  4. **Bayesian updating in Paper 4** updates the **parameters of the relationship** (the CPT probabilities), not a state: standard parameter learning in Bayesian networks with the expert-elicited CPT as prior (for example Dirichlet distributions per CPT row; Koller & Friedman, 2009). Paper 4's statement that vulnerability is not a static indicator holds: the relationship learns from real operation.
  5. Paper 4 §2.1 inputs are **not** a separate vulnerability concept: demographic and socioeconomic factors enter through Social Susceptibility; baseline accessibility and capacity enter through the simulation that produces `GE` and `SL`, and through Need Pressure.
  6. **Vulnerability is not risk.** Averaging vulnerability over scenarios weighted by their probability of occurrence gives **risk**, which is a separate output. Vulnerability results must never depend on which scenarios happen to be included in a run.
- **Rationale.** Keeps Paper 3's definition almost unchanged, removes double counting in Paper 4, avoids overlap with Social Susceptibility, makes results independent of the chosen scenario set, and turns Paper 4's updating into standard, well-documented parameter learning. The earlier proposal (vulnerability as an average over scenarios) was rejected because it conflates vulnerability with risk and depends on the scenario set.
- **Additions agreed with this decision.**
  1. **Maps at reference scenarios.** Vulnerability is mapped at standardised **reference scenarios** (for example minor, moderate, severe disruption), so that areas and groups are compared at the same intensity. Risk maps are produced separately, only if disruption probabilities become available.
  2. **Weight of experts against data:** new question OQ-27.
  3. **Observation node.** Because Vulnerability is latent, Paper 4 needs a measurement node `P(ObservedConsequence | V)` stating what is observed for each vulnerability level. To be specified together with OQ-18.
- **Spec impact.** Paper 3 §2 and §17 (wording), Paper 3 §25–26 (maps at reference scenarios), Paper 4 §2.1, §8, §10 and the diagram in §15 must be rewritten. CLAUDE.md invariant 2 is updated accordingly.

## Paper 4 (operations, dynamics, resilience)

**OQ-17 (DBN structure, §5, §12).** How facility functional state is derived from indicators (rules or learned), their thresholds, the time-slice length and the DBN topology (for example first-order Markov) are not specified. Status: open.

**OQ-18 (observed consequence, §9).** How observed group consequence is computed from tickets, and against which denominator. Tickets observe demand, not hidden need. Since OQ-16, this also includes the measurement node `P(ObservedConsequence | V)` that links the latent Vulnerability to what tickets show. Status: open.

**OQ-19 (resilience estimation, §13).** How the five trajectory indicators combine, how continuous trajectories map to `P(Resilience)`, and the baseline reference level are open. The research description states that final selection and weighting of indicators is part of the research. Status: open.

**OQ-20 (resource mobilisation, §6).** Parameters, activation delays and capacity limits of volunteer and other additional resources are not specified, and Paper 3 explicitly excludes adaptive capacity. Status: open.

**OQ-27 (weight of expert priors against observed data; raised with OQ-16).** When the Vulnerability CPT is learned from observed disruptions, the expert-elicited CPT acts as a prior with an equivalent sample size: how many observed disruptions should it take to move the experts' judgement? Options include a fixed equivalent sample size per CPT row, elicited confidence per row, or hierarchical pooling across units and groups. Also open: how to handle the small number of real disruptions and the dependence between observations in the same disruption. Status: open.

**OQ-21 (re-identification risk, §4.1).** Tickets are anonymous, but spatial unit, group and timestamps together can identify people in small units. Decide minimum cell sizes (k-anonymity), retention and aggregation rules before collecting any real data. These rules also limit how finely observations can be used for learning (OQ-8, OQ-16). The ticket field "first request in this period" (OQ-8) must not become an identifier. Status: open.

## General

**OQ-22 (terminology).** "ΤΚ" (Local Community) versus a generic spatial unit; group names (Low-income, Economically vulnerable); language of identifiers and documentation. Status: open.

**OQ-23 (Digital Twin wording).** Paper 1's conclusion calls the result a "probabilistic baseline Digital Twin", while the research description says a Digital Twin is not assumed from the start. Keep wording consistent in README and docs. Status: open.