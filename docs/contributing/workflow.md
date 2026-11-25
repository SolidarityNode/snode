# Ticket workflow

> The rules are in [AGENTS.md](../../AGENTS.md#workflow-for-tickets) and the [contributing guide](../../CONTRIBUTING.md#workflow); this page shows how a ticket moves. Live state: the [Kintsugi board](https://github.com/orgs/SolidarityNode/projects/6).

```mermaid
flowchart TB
    I["Issue<br/>acceptance criteria, spec section, OQ-n"] --> Q{"Spec clear and<br/>OQs decided?"}
    Q -- no --> RQ["Comment the question on the issue<br/>label needs-spec; stop"]
    RQ --> DEC["Decision in open-questions.md or an ADR<br/>(paper-revisions.md if the method changes)"]
    DEC --> Q
    Q -- yes --> B["Branch feat/ISSUE-short-name"]
    B --> C["Small signed-off Conventional Commits<br/>tests for every acceptance criterion"]
    C --> D["Docs: user guide page, CHANGELOG Unreleased,<br/>Mermaid diagrams, specs cross-reference"]
    D --> L["make lint test (and make docs-build)"]
    L --> PR["Pull request from the template<br/>Closes #N, How to test (UAT), licences"]
    PR --> CI["CI: lint, tests, e2e, docs, licences, DCO"]
    CI --> U["UAT by the maintainer (make uat)"]
    U -- failed --> F["comment + label uat-failed"] --> C
    U -- passed --> M["Merge by the maintainer<br/>(never by the author)"]
```

## Board columns

| Column | Meaning |
| --- | --- |
| Todo | ready: spec clear, no blocking open question |
| In progress | someone has a branch for it |
| Done | merged; listed under **Unreleased** in the changelog until the next release |

Tickets that wait for a decision carry `needs-spec` or `blocked`; per-paper work carries `paper:1` … `paper:4` and the paper's milestone ([roadmap](../roadmap.md)).

## Releases

After merges accumulate, the maintainer cuts a release: [Releasing](../releasing.md).
