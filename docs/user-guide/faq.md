# Frequently asked questions

> Describes platform version **0.1.0**.

## Why does every result say "diagnostic model"?

Because no research method is implemented yet. The only model, `diagnostic-v0`, computes simple things (travel times on the network after the scenario's changes, and random noise) to check that the platform works: scenarios are applied, runs are reproducible, uncertainty is stored and displayed, exports are complete. **Its numbers are not accessibility, need, vulnerability or resilience**, and every page says so. The research methods come paper by paper ([roadmap](../roadmap.md)); each needs its open questions decided first ([open questions](../specs/open-questions.md)).

## What is the seed?

Results come from Monte Carlo simulation: many random draws. The **random seed** (a whole number) fixes those draws, so the same run gives exactly the same numbers again. If you give none, the platform draws one and records it, so the run stays reproducible. Change the seed only to check that conclusions do not depend on one particular set of draws.

## Why did my run open at once, without computing?

The platform found a run with exactly the same inputs: the same scenario version, data version, code, model, seed and settings. A run never changes, so the existing one is the answer: it opens instead of computing again. A failed or cancelled run is never reused, and a run whose results file fails its integrity check is not reused either (the page says why).

To get a new run, change something that matters: a new scenario version, another seed, or new data.

## What is the edge effect?

People near a municipal boundary often use facilities on the other side. The study area includes a **buffer** of neighbouring units for this reason. If a neighbouring municipality has **no facility data**, results for the units next to it may be biased (for example travel times that are too long). Those units get an orange outline and the warning "⚠ edge effect (OQ-28)" (φαινόμενο ορίου). The warning disappears when the hub adds the neighbour's facilities; how large the buffer should be is still an open question (OQ-28).

## Why is a result "Not reported" for some units?

They are buffer units: they belong to a neighbouring municipality and are in the data only so that cross-boundary use is counted. Results are reported for your own (core) units only.

## Why are some changes "recorded only"?

The scenario format can already hold changes that no method uses yet (disruption severities, travel-time changes, new roads, population changes). They are saved and shown, so nothing is lost, but they do not change results until the methods that use them exist ([Scenario editor](scenario-editor.md#what-has-an-effect-today)).

## Can I upload my own data?

No. Data comes from the hub as data packages, imported by an administrator, so every installation uses checked data with known sources. To test a change, write a scenario; to correct the data, send the correction to the hub ([Data packages and updates](data-updates.md)).

## Is any personal data stored?

No. The platform holds synthetic or aggregated data only. The future operational data (anonymous request tickets) records only the area, group, service, facility and times, and nothing is stored until the privacy rules for small areas are decided ([ADR 0010](../adr/0010-ticket-privacy.md), OQ-21).

## Where do I report a problem?

Tell your administrator, or open an issue on GitHub with the steps, what you expected, what you saw, and the build line from the footer. Never paste passwords or real personal data ([UAT guide](../uat/README.md#6-reporting-a-problem)).
