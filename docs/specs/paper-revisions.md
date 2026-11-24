# Paper revision notes

> Working notes for writing the final versions of Papers 1–4. Each entry records **what must change in the paper text**, **why**, and the decision it comes from (`OQ-n` in `open-questions.md`, where the full reasoning and rejected options are kept). Update this file whenever a decision is taken. Entries are written so they can be turned directly into methods, discussion and limitations sections.

## Cross-cutting

### Notation (OQ-1)
- **Change in all papers:** `i` spatial unit, `f` facility, `g` group, `s` service, `m` transport mode, `c` scenario, `t` time, `l` state of a discrete variable. Demand, supply and gap belong to the spatial unit `i`; travel time is `T_if^{g,m}`. Other symbols: `k` intensity, `p` need prevalence, `τ` take-up, `P(·)` probability.
- **Specifically:** Paper 1 §5–8 replaces `j` (used both as facility and as demand location) with `f` and `i`; Paper 3 replaces `s` for scenario with `c`.
- **Suggestion for the papers:** a shared notation table, identical in all four, in the methods section.

### Units of measurement (OQ-24)
- **Change:** state that need, capacity, supply, gap and loss are measured in **service units per reference period** (visits, appointments or hours, defined per service), and that need is `people with need × intensity` (`N × k`). Quantities of different services are never summed.
- **Why:** capacity data (places, staff, throughput) is naturally in service units, and intensity differs strongly between groups; counting only people hides intensity, counting only units hides how many people are affected.
- **Methods text:** introduce `N`, `k` and the reference period (open, OQ-25) in the data and notation section of Paper 1 and reuse them in Papers 2–4.
- **Limitation to discuss:** severity differences between services are not weighted (N-24a).

### Delay counts as loss beyond a threshold (OQ-26)
- **Change:** each service has a maximum acceptable waiting time; a request not fulfilled within it counts as unmet need. Threshold values set with domain experts.
- **Where:** Paper 4 §4.2 (overdue and expired requests), and the definition of unmet need in Papers 1 and 3.

## Paper 1: Accessibility and service capacity

### §6 Demand rate means visible use under average conditions (OQ-8)
- **Change:** define `DemandRate` explicitly as the share of the group that **makes requests** for the service under average conditions (typically a national or regional rate), not the share that needs it. Need prevalence is introduced in Paper 2.
- **Why:** keeps Paper 1 consistent with the hidden-need decomposition of Paper 2. State that estimated demand applies an average rate and is therefore not a local observation of use.
- **Also:** demand becomes `N × k` in service units (OQ-24).

### §8 Service Gap covers unmet expressed need only (OQ-8)
- **Change:** state that the Service Gap concerns need that is **expressed** (requests) but not met; need that is never expressed is the subject of Paper 2. The two never overlap.

### §7 Capacity allocation by 2SFCA (OQ-2)
- **Change:** replace `C_ij^effective = C_i^functional × w(T_ij)` and `Supply_j^g = Σ_i C_ij^effective` with a two-step floating catchment area allocation: each facility's functional capacity is shared among the units and groups that reach it, in proportion to access-weighted demand; groups compete for the same capacity.
- **Why (methods/discussion):** the original formula counts a facility's full capacity for every area that reaches it, so supply exceeds what the facility can deliver and the Service Gap is underestimated. 2SFCA conserves each facility's capacity, does not redistribute demand after a capacity loss (consistent with Paper 3, which excludes adaptive redistribution), makes no behavioural assumption beyond `w(T)`, and is cheap enough for Monte Carlo.
- **Limitations to discuss:** demand inflation when a unit lies in several catchments; a unit may receive more supply than its demand while capacity elsewhere is short.
- **Future work to mention:** 3SFCA as a refinement (N-2a); capacity-constrained allocation as an alternative model in sensitivity analysis, noting it assumes coordinated allocation and understates the gap (N-2b).

### Open items affecting Paper 1
- Access weight `w(T)` (OQ-3), relation of the deterministic gap to the BBN (OQ-4), combining transport modes (OQ-5), group definitions and overlap (OQ-6), discretisation and BN engine (OQ-7).

## Paper 2: Hidden need

### §1.1, §2, §10, §12 Hidden need as non-take-up (OQ-8)
- **Change:** decompose need into **need prevalence** `p` (share of the group that needs the service) and **take-up** `τ` (share of those with need who **express** it by making a request, whether or not they are then served).
- **Change:** define three non-overlapping kinds of need: **hidden** (never expressed; this paper), **unmet expressed** (requests not fulfilled; Service Gap in Paper 1, Service Loss in Paper 3) and **met**. Explain that defining take-up as "being served" would make capacity shortages look like hidden need and count the same unmet need twice. Hidden need in people `= Population × p × (1 − τ)`; share of the group with hidden need `= p × (1 − τ)`; total need `= Population × p` (in units `× k`).
- **Change:** the BN target node is the **level of non-take-up** (`1 − τ`), with states as ranges (for example 0–20 %, 20–50 %, 50–80 %), with four parents: Social Susceptibility, need-based gap (OQ-10), access deterrence and alternatives outside the network (OQ-11).
- **Change:** report hidden need as a share of the group **with an interval** from Monte Carlo, for example "7–17 % of the group (90 % interval)".
- **Why (methods/discussion):** the research question is "what share of the group has need that is not visible"; defining hidden need relative to estimated demand would make it vanish for groups that barely appear in services, possibly where it is largest. The decomposition separates two questions experts can answer more reliably, bounds hidden need by the population, connects to the non-take-up literature and to survey data on need or unmet need, and lets observed use (administrative records, tickets) update take-up.
- **Expert elicitation text:** phrase questions as frequencies, for example "out of 100 older people who need care, in an area with low accessibility and few alternatives, how many do not receive it?".
- **Learning from observations (methods):** observed use (administrative records now, tickets in Paper 4) enters as evidence and updates the **parameters** of `P(non-take-up | parents)` by Bayesian parameter learning, pooling across units with similar characteristics, with the expert CPT as prior (same mechanism as the vulnerability relationship in Paper 3/4). Updating per unit is avoided because counts are small and privacy rules restrict them. Where aggregate administrative figures exist, total visible need is calibrated against them; local differences are allowed.
- **Why not a local consistency check (discussion):** Paper 1 demand applies an average rate, so local departures of visible need from it are exactly what the method should reveal; enforcing equality would determine take-up arithmetically and make the BN redundant. The ratio of visible need to Paper 1 demand is shown only as a descriptive indicator of where local use departs from the average.
- **Limitations to state:**
  - *Identifiability:* use data observe only how many requests are made (`p × τ × k`), not need and take-up separately; hidden-need estimates rest on independent information about `p`. Report sensitivity of hidden need to `p`.
  - *Recording completeness:* unrecorded requests (facilities or channels outside the system) would lower observed use, underestimate take-up and overestimate hidden need; only facilities with full or known recording coverage are used for learning.
  - *Persons versus requests:* anonymous tickets count requests; a "first request in this period" flag (no identifier) is used to count people.
- **Data:** source of `p` to be determined (candidates to check: EU-SILC, EHIS, SHARE; usually national or regional), otherwise expert elicitation.
- **Future work to mention:** intensity of hidden need may differ from visible use (N-8a); small area estimation of unmet need from surveys as independent validation (N-8b); a direct validation study through outreach (home visits or telephone survey in sample units) and referrals from other actors, since tickets by definition never show hidden need (N-8c).

### §6–7 Social Susceptibility per unit, group and service (OQ-9)
- **Change:** write `SS_{i,g,s}`. Indicators, or their weighting, may differ by service; group-definition variables are still never reused.
- **Why:** social characteristics vary spatially, and a group is not equally prone to unmet provision for every service (for example older people living alone for home care versus employment services).
- **Limitation to state:** unit-level indicators may be coarse or based on small counts; their uncertainty is propagated by Monte Carlo.

### §8–10 Parents of non-take-up without overlap (OQ-11)
- **Change (§8 diagram):** four parents with no edges between them; remove the arrows from Social Susceptibility to Service Gap and Accessibility, which contradict §6.2.
- **Change (§9.3):** accessibility enters only as **access deterrence**, the burden of reaching the service that discourages seeking it (for example travel time to the nearest facility).
- **Change (§9.4):** alternatives are only options **outside** the modelled facility network (private services, family, NGOs, parishes), matching §1.1. Alternative facilities inside the network are already part of the need-based gap.
- **Why (methods/discussion):** the need-based gap uses 2SFCA supply, which already includes accessibility and all reachable facilities; defining accessibility and alternatives as in the original §9.3–9.4 would count the same information twice and confront experts with combinations that hardly occur. The two remaining mechanisms ("too far to ask", "covered elsewhere") are distinct from network adequacy.
- **Limitation to discuss:** data on outside alternatives may be scarce; initial values from experts. CPT size (81 rows) is handled in the elicitation protocol (intermediate nodes or parametric methods, OQ-7).

### §9.2 Need-based gap replaces Paper 1 Service Gap as parent (OQ-10)
- **Change:** the parent of non-take-up is the **need-based gap** `max(0, Population × p × k − Supply)`, using Paper 1 supply but comparing it with total need, instead of reusing Paper 1's demand-based Service Gap "not recomputed".
- **Why (methods/discussion):** Paper 1 demand reflects visible use, which already contains take-up. Using its gap as a parent creates a loop: low take-up gives low demand, a small gap, and hence an inferred low non-take-up, so the group with the most hidden need would appear to have the least. People are discouraged by shortage relative to everyone who needs the service, not relative to current users.

### §4, §22 Total need formula
- **Change:** replace `EstimatedTotalNeed = EstimatedDemand + ExpectedHiddenNeed` with `ETN = Population × p × k`, explaining that the BN splits total need into visible and hidden parts.
- **Why:** removes the dependence of total need on estimated demand and simplifies the double-counting concern (OQ-10).

## Paper 3: Vulnerability

### §2, §17 Vulnerability as a relationship (OQ-16)
- **Change:** define the vulnerability of a group as **the relationship that turns a disruption into consequences for that group, given its social susceptibility**, represented by the CPT `P(V | GE, SL, SS)`. A value `V_{i,g,s,c}` is that relationship **evaluated at scenario `c`**.
- **Why (methods/discussion):** a single vulnerability number depends on the chosen disruption intensity; the relationship does not. The framing parallels vulnerability and fragility curves in seismic engineering (verify literature, for example HAZUS, before citing). It also allows Paper 4 to use and learn the same relationship.
- **Add:** a sentence distinguishing **vulnerability** from **risk** (vulnerability weighted by disruption probabilities), and stating that results do not depend on which scenarios are run.

### §14–15, §28 Service Loss measures only the disruption (OQ-12)
- **Change:** introduce the baseline gap `PUN⁰ = max(0, ETN − AS⁰)` and define disruption loss as `ΔPUN = PUNᴰ − PUN⁰`. Service Loss becomes `SL = (PUNᴰ − PUN⁰) / ETN`.
- **Change:** add Relative Service Loss `SL′ = (PUNᴰ − PUN⁰) / min(ETN, AS⁰)` as a secondary indicator for maps and sensitivity, not a BN node.
- **Why (methods/discussion):** with the original `PUN / ETN`, a scenario with zero severity still shows loss wherever a baseline gap exists, so the baseline gap leaks into Vulnerability, contradicting §6, which excludes Need Pressure as a parent to avoid double counting. The new definition gives zero loss when nothing happens, keeps each parent of Vulnerability measuring only its own aspect, and matches the resilience literature, where loss is measured against pre-event performance (Bruneau et al., 2003), so Paper 4's `ServiceLoss(t)` starts and ends at zero.
- **Worked example for the paper:** `ETN` 800, `AS⁰` 700 → `ASᴰ` 500: original 0.375, new `SL` 0.25, `SL′` 0.286; and with no disruption (700 → 700): original 0.125, new 0.
- **Limitation to discuss:** `SL` understates the consequence for groups with very low baseline coverage (`AS⁰` 100 → 0 gives `SL` 0.125, `SL′` 1.0); hence `SL′` is reported.
- **Expert elicitation text:** "Service Loss High" means that the disruption left a large additional share of the group's total need uncovered.
- **Keep §6 as is:** Need Pressure remains outside the core BN and is examined in sensitivity analysis.

### §13–15 Depth of loss and rationing (OQ-24)
- **Change:** add rationing as a scenario parameter with two bounding cases, **uniform** (everyone receives proportionally less) and **concentrated** (some are fully served, others not at all), and report per-person loss indicators in the Foster–Greer–Thorbecke style (Foster, Greer & Thorbecke, 1984; verify): **breadth**, **depth**, **severity**. These are outputs, not BN parents.
- **Why:** the same loss in service units can mean everyone losing a little or a few losing everything; without operational data the pattern is unknown, so it is bounded rather than assumed.
- **Future work to mention:** breadth as a BN parent only if sensitivity shows it matters (N-24b).

### §12, §17, §21 Susceptibility index and vulnerability states (OQ-9, OQ-15)
- **Change:** write `SS_{i,g,s}` (from Paper 2) instead of `SS_g`.
- **Change:** Vulnerability has three states (Low, Medium, High); remove "Very High" from the elicitation table in §21. Discretisation thresholds for Group Exposure and Service Loss remain to be set.

### §25–26 Maps at reference scenarios (OQ-16)
- **Change:** present vulnerability maps at standardised **reference scenarios** (minor, moderate, severe) so areas and groups are compared at the same intensity. Risk maps only if disruption probabilities become available.

### Open items affecting Paper 3
- Affected population and catchments (OQ-13), disrupted service function (OQ-14), states and thresholds (OQ-15).

## Paper 4: Resilience

### §2.1, §8, §10, §15 Vulnerability used and learned, not redefined (OQ-16)
- **Change:** remove the separate "baseline vulnerability" built from demographic, socioeconomic, accessibility and capacity factors. State that demographic and socioeconomic factors enter through Social Susceptibility, and baseline accessibility and capacity through the simulation producing Group Exposure and Service Loss.
- **Change (§8):** Expected Group Consequence is Paper 3's vulnerability relationship evaluated at the **observed** `GE(t)` and `SL(t)` derived from tickets and the territorial functional state. The disruption enters once.
- **Change (§10):** Bayesian updating learns the **parameters** of the relationship (CPT probabilities) from observed consequences, with the expert-elicited CPT as prior (for example Dirichlet per row; Koller & Friedman, 2009), instead of updating a vulnerability state.
- **Add:** a measurement node `P(ObservedConsequence | V)` linking the latent vulnerability to what tickets show (with OQ-18).
- **Update the diagram in §15** accordingly.
- **Why (methods/discussion):** combining a scenario-based vulnerability with the functional state would count the disruption twice; a scenario-free baseline vulnerability would duplicate Social Susceptibility. Parameter learning keeps the statement that vulnerability "is not a static indicator" while using a standard, well-documented method.
- **Open:** weight of expert priors against data, small number of real disruptions, dependence between observations (OQ-27).

### §11–13 Trajectories start at zero (OQ-12)
- **Change:** define `ServiceLoss(t)` with the Paper 3 definition (loss relative to pre-event performance), so trajectories start at zero and full recovery returns to zero.

### §4.2, §9 Rationing observed from tickets (OQ-24)
- **Add:** the actual rationing pattern (how shortage is spread among people) is estimated from tickets (fulfilled, overdue, expired requests per person), replacing the bounding cases of Paper 3.
- **Add:** tickets inform take-up `τ` (Paper 2) once need prevalence `p` is known, through learning of the Paper 2 CPT parameters, using only facilities with full or known recording coverage.

### §4.1 Ticket fields (OQ-8, OQ-6, OQ-21)
- **Add:** a "first request in this period" flag (yes/no, no identifier) so that people can be counted without being identified; a rule for tickets of people belonging to several groups (OQ-6); and recording coverage per facility and period.

### Future work to mention
- Capacity-constrained allocation as a model of redistribution and resource mobilisation (N-2c); severity weighting by service (N-24a).

### Open items affecting Paper 4
- DBN structure and time step (OQ-17, OQ-25), observed consequence (OQ-18), resilience estimation (OQ-19), resource mobilisation (OQ-20), privacy of tickets (OQ-21).
