# How SolidarityNode works: the main ideas

For municipal staff who use the platform: analysts, viewers and administrators. No technical
background is needed. Words in **bold** are the names you see on screen.

## The short version

- A **data package** says *what is true*: the official data of the study area.
- A **scenario** asks *what if*: a hypothesis on top of that data.
- A **run** computes the answer: one scenario on one version of the data, kept unchanged
  forever.

## Data package: what is true

A data package holds the official, shared data of the study area: the spatial units and their
population by social group, the facilities and the services they offer, and the road network.

- It is **built and published by the hub** (the team that prepares data for all
  municipalities), from official and open sources, with a processing note for every step.
  What you send to the hub and how an update arrives: [Working with the
  hub](user-guide/hub-updates.md); the hub's own screens: [Hub](user-guide/hub.md).
- It is **imported only by an administrator** of your installation (**Admin** → **Data
  packages**). Analysts and viewers never upload data.
- It is **versioned**: every import creates a new **data version** (for example 1.0.0, then
  1.1.0). Earlier versions are kept, so an administrator can make an earlier one active again.
- One data version is **active**: new scenarios and new runs use it.
- The **Study area** page shows the active version, its licences, and how good each layer is
  (verified by the municipality, open data, estimated or missing).

**Analysts do not upload data.** To try a change, such as a closed road, a new facility or
more staff, write a **scenario**. If the data itself is wrong or out of date (a facility has
closed, a real new facility opened, a road number is wrong), send the correction to the hub.
It arrives in the next version of the data package, for everyone.

## Scenario: what if

A scenario is a hypothesis: a list of changes on top of the data. Examples: "road E02 is
closed", "facility F3 has one more staff member", "a new community centre opens at node N-B2".

- A scenario never copies or changes the data; it only describes changes relative to it.
- It is **created against one data version** (shown on the scenario page) and checked against
  it: every facility, road and unit it names must exist.
- It has an **owner** and a **visibility**. **Private**: visible to its owner and to
  administrators (administrators run the installation and can see everything). **Shared**:
  visible to every user, including viewers.
- Every save creates a new **version** of the scenario; earlier versions stay, so runs can
  always say exactly which version they used.
- Some changes are **recorded only** for now (changes to road travel times, new roads,
  population changes): they are saved and listed, but have no effect on results yet.

## Run: the answer, kept unchanged

A run is one execution of one scenario version on one data version.

- It records everything needed to repeat it: scenario and version, data package and version,
  code version, model and version, random seed and settings.
- It **never changes** after it finishes. A new answer always means a new run.
- Running the same scenario version on the same data with the same settings again does not
  compute anything: the existing run opens.
- Results always come with their uncertainty: a central value (the median) and an interval.
- Until research models are added, results come from a **diagnostic model** that only checks
  that the platform works. They are not research results, and every page says so.

## When the data is updated

When an administrator imports a new data version, or makes an earlier one active again:

1. A **baseline run** (no changes) is queued on the new data.
2. Every scenario is **checked again** against the new data. A scenario that names something
   that no longer exists (for example a closed facility) shows **Needs attention** and cannot
   run until it is edited.
3. Existing runs stay as they were: they keep showing the data they used. The run page says
   "This run used data 1.0.0; the active data is 1.1.0." and offers **Rerun on data 1.1.0**.
4. On the scenario page, "Created against data 1.0.0; active data is 1.1.0." reminds you that a
   new run uses the active data.
5. In the **Scenarios** list, a scenario without a run on the active data shows **Latest run on
   data 1.0.0**, and a scenario that was never run shows **Not run yet**.

## Who does what

| Role | Can |
| --- | --- |
| **Viewer** | See shared scenarios and their runs: results, map, table, exports. Cannot create, edit or run scenarios; to see results of a scenario that was never run, ask an analyst to run it. |
| **Analyst** | Everything a viewer can, plus create, edit, run, duplicate and share their own scenarios, and run the baseline. |
| **Administrator** | Everything an analyst can, on every scenario (including other users' private ones), plus manage users, import data packages and choose the active data version. |
| **Hub** (outside your installation) | Onboards municipalities, curates their facilities, builds and publishes data packages; receives corrections to the data ([Hub](user-guide/hub.md)). |
