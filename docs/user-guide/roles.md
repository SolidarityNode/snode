# Roles

> Describes platform version **0.1.0**.

| Role | Greek | Can |
| --- | --- | --- |
| **Viewer** | θεατής | See shared scenarios and their runs: results, map, table, exports. Cannot create, edit or run scenarios. |
| **Analyst** | αναλυτής | Everything a viewer can, plus create, edit, run, duplicate and share their own scenarios, and run the baseline. |
| **Administrator** | διαχειριστής | Everything an analyst can, on every scenario (including other users' private ones), plus manage users, import data packages and choose the active data version. |
| **Hub** (outside your installation) | | Builds and publishes data packages; receives corrections to the data. Planned for v0.2 ([roadmap](../roadmap.md)). |

**Private** scenarios are visible to their owner and to administrators; **shared** scenarios to every user. A run inherits the visibility of its scenario: a run of a private scenario is "not found" for other users.

The same table, with the reasons, is in [Concepts](../concepts.md#who-does-what); the decision is [ADR 0015](../adr/0015-authentication-and-roles.md).
