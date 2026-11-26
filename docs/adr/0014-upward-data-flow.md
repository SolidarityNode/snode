# 0014. Upward data flow from municipalities to the hub

- Status: Part A (facility corrections) accepted for v0.2, to be revisited; Part B (aggregated indicators) proposed, stub, needs a human decision
- Date: 2026-11-24 (Part A proposed and accepted for v0.2: 2026-11-26)
- Related: Spec 00 §3 (Deployment), OQ-21, OQ-8, OQ-16, OQ-27; ADR 0006, 0010, 0012, 0013, 0015

Two kinds of data could travel from a municipal installation to the hub: **corrections of
facility data** (Part A, proposed for v0.2) and **aggregated indicators** from operation
(Part B, not decided). They have different privacy profiles and are decided separately.

## Part A: facility corrections submitted from a municipal installation

**Status of this part: Accepted for v0.2, to be revisited** (maintainer's answers to decisions
15–27 in PR #14, 2026-11-26). Points marked *(v0.2)* are simplifications to revisit.

### Context

Since the hub onboarding PR (#14) a municipality sends its facility file to the hub team, and a
hub analyst uploads it (DP-004, `docs/data-processing/facility-import.md`). The maintainer has
decided (2026-11-26):

- **No e-mail:** submissions travel between installations through the platform, with no e-mail
  notifications; status is shown in the UI.
- **Who submits:** **analysts and administrators** of a municipal installation; viewers cannot.
  A submission is a **proposal** to the hub and never changes the active data of the
  installation: only an administrator imports packages, as before.
- **Nothing changes automatically:** the hub validates a submission automatically, a hub
  administrator approves or rejects it and publishes the next package version, and the
  municipal administrator imports it with the existing preview and confirm.
- **Scope of v0.2: facilities only** (template columns, CSV and XLSX, and a manual edit form).
  Boundaries, units, population and network come later.

### What may leave an installation (decision 16)

- **Reference data about organisations**: facility rows in the import template, after the
  personal-data columns and values have been dropped locally (A7). Nothing else.
- **Never**: data about people or about individual requests (for example the request log of the
  Paper 4 pilot, tickets), and **never scenario results**, except what Part B may decide later.
  Part A does not relax Part B: aggregated indicators still do not leave an installation until
  Part B and ADR 0010 are decided.
- ADR 0012's rule holds: **every connection is opened by the installation**; the hub never calls
  an installation and holds no credentials *for* it (it keeps only what it needs to check the
  installation's token, A2).

### A1. Connection (decision 17)

- The installation calls the hub API over **HTTPS**. The hub address is set **only in
  configuration** (`SOLIDARITYNODE_HUB_URL`), never from the UI, so a user cannot make the
  server call an arbitrary address (SSRF).
- With `APP_ENV=production` the settings refuse a plain `http://` URL except `localhost` /
  `127.0.0.1` (checked by `make check-config`). Development allows `http` between the local
  compose projects.
- The hub serves the installation API under its own prefix (`/hub/installation/…`),
  authenticated by the installation token in an `Authorization: Bearer` header, not by session
  cookies; the frontend proxy passes it through unchanged.

### A2. Trust between installations (decision 18, 25)

- A hub administrator **registers** each installation (name, the one study area it serves) and
  **issues an installation token**: random (256 bits), shown **once**. The municipal
  administrator stores it as the secret `SOLIDARITYNODE_HUB_TOKEN` in `.env` (never in git,
  never logged, never shown in the UI; the UI only says "token present: yes/no") and restarts
  the backend and worker; the admin guide (`docs/user-guide/hub-updates.md`) says how, and how
  to check the connection.
- **Scope** of a token: submit changes for the **core** municipalities of its study area only
  (not its buffer); read and withdraw **its own** submissions; list and download the packages of
  **its own** study area. Nothing else.
- *(v0.2)* **One active token per installation**: issuing a new token revokes the old one at
  once; revocation takes effect at once. The hub records the last contact (time and the client
  address its proxy reports, ADR 0015).
- What the hub stores (decision 20): `token_hash = SHA-256(token)` to authenticate API calls, and
  `offline_key = HMAC-SHA256(key = token, message = "solidaritynode offline submission v1")` to
  verify offline files (A3). Neither gives back the token.
- **An attacker who reads the hub database** cannot call the hub API as an installation (the
  token cannot be recovered from either value), but can **forge offline submission files** for
  that installation with `offline_key`. Such files still go through the hub's validation and a
  hub administrator's review, are marked "offline" in the review, and can only be uploaded by a
  hub administrator. Rotating the token changes both values.
- Failed token checks get one generic 401.

### A3. Offline fallback (decision 20)

- An installation without a network path to the hub exports a **submission file**: a `.zip`
  with `submission.json` (the same content as an online submission: the **sanitised** rows, the
  locally computed changeset and the comment, never the original upload), `manifest.json` with
  its SHA-256, and `signature.txt` = HMAC-SHA256 of `submission.json` keyed with `offline_key`
  (derived from the token as in A2, so installation and hub compute the same key).
- A hub administrator uploads it; the hub checks the installation, its token not being revoked
  and the HMAC, then treats it exactly as an online submission (same validation, same
  changeset, same idempotency by UUID). Status travels back when the installation is next
  online (or not at all, if it never is).

### A4. Lifecycle and status (decision 26)

```
draft → sent → received → rejected_by_validation
                        → pending_review → approved → published_in <version> → imported
                                         → rejected
draft | sent | received | pending_review (before review starts) → withdrawn
```

- `draft`: saved and validated locally, not sent. `sent`: queued for the worker or being
  retried (A5); the last error and next try are shown. `received`: the hub stored it.
  `rejected_by_validation`: the hub's own validation found errors. `pending_review` →
  `approved` / `rejected` by a hub administrator, **with a comment** shown in the municipality.
  `published_in <version>`: a published package of the installation's study area lists the
  changeset in its manifest `provenance`. `imported`: the installation imported that version or
  a later one.
- `withdrawn`: the submitter or a municipal administrator withdraws it, **until the hub starts
  reviewing it** (a hub administrator opens it for review); after that the hub refuses.
- Every transition stores who (the municipal user's pseudonym, A7, or the hub administrator's
  username) and when.

### A5. Synchronisation (decision 21)

- A worker job `hub_sync` sends queued submissions, withdrawals and polls the hub for status
  changes and new package versions. *(v0.2)* The worker gets a **small periodic tick** that
  enqueues `hub_sync` every `SOLIDARITYNODE_HUB_SYNC_SECONDS` (default **300**) when none is
  queued or running; the Submissions page has **Check now**, which only queues the job (no call
  from a request handler).
- **At most one sync runs at a time** (checked when queuing, plus a database advisory lock while
  it runs); it has a **heartbeat** like every job (ADR 0006).
- **Exponential backoff** while the hub is unreachable (1 min, doubling, at most 1 h); the
  submission stays `sent`.
- **Idempotent resend:** every submission has a UUID chosen by the installation; a second send of
  the same UUID returns the existing changeset.
- **Switch off:** `SOLIDARITYNODE_HUB_SYNC=false` (offline installations), or no hub URL; then
  nothing is called and submissions are exported as files (A3).
- This hits ADR 0006 revisit triggers 3 and 4. No general scheduler now: the Paper 4 scheduled
  runs (OQ-31) will reopen the scheduler question (note in ADR 0006).

### A6. New package versions (decision 22)

- The sync job lists the packages of the installation's study area. A newer version than the
  active one is shown to the **administrator** as "a new version is available" with its
  changelog. **Download** is on the administrator's request (a job), verifying the archive's
  SHA-256 against the hub's package record; the existing **preview and confirm** then applies.
- *(v0.2)* **Checksums over TLS are enough**, because the installation downloads on its
  administrator's request, from the hub address in its configuration, with its token, over
  HTTPS, and an administrator previews and confirms every import. **Signing is required before
  any automatic import** (and remains advisable for packages passed around outside the
  platform; ADR 0013 "Consequences").

### A7. Privacy (decisions 19, 23)

- Validation runs **locally first**, with the **same validator code** as the hub, on the
  facilities of the installation's active package; personal-data columns and values are dropped
  **before anything leaves the municipality**. What is sent: the sanitised rows (template
  columns only), the computed changeset and the comment; **never the original file**. The hub
  validates again. A test checks that the same file gives the same report in both roles, except
  for the location checks that depend on each side's data.
- The validator is **one backend module used by both roles**: parsing, personal-data and row
  checks are shared as they are; location checks read the hub's curated features in the hub and
  the active data version in the installation (`core` keeps model code only).
- **Who submitted** (decision 19): a **stable pseudonymous id per user** (for example
  `u-3f9c2a1b`), created by the installation, plus the role. Only the installation can resolve
  it; its **administrators** see the mapping to usernames. The hub stores "municipality X
  (installation Y, user u-…, analyst)".

### A8. Conflicts (decision 24)

- Each item records the **package version it was based on** and the facility's values in that
  package. On receipt, the hub compares them with the facility's current state.
- If the hub changed the facility since, the item is marked **conflict** and shown in the review
  with the three states (municipality's package, hub now, proposed); it is never overwritten
  silently. The hub administrator **resolves each conflicting item** (take the municipality's
  change, or keep the hub's value) before approving, and the **submitter sees how each conflict
  was resolved**.

### A9. "Complete list" from a municipality

- Allowed: the municipal UI asks for the same confirmation as the hub (type the number of
  facilities that will be closed); the hub review shows the closures prominently and asks for the
  count again before approving.

### Consequences (Part A)

- New settings in the municipal installation: `SOLIDARITYNODE_HUB_URL`,
  `SOLIDARITYNODE_HUB_TOKEN` (secret), `SOLIDARITYNODE_HUB_SYNC`,
  `SOLIDARITYNODE_HUB_SYNC_SECONDS`.
- New tables: in the hub, installations (token hash, offline key, last contact) and submission
  fields on changesets; in the installation, submissions with their status history and the
  user pseudonyms.
- ADR 0006 gains the periodic tick; ADR 0012 and 0015 gain the installation token as a second
  kind of credential.
- Part B (aggregated indicators) is unchanged and not decided.

## Part B: aggregated indicators (not decided)

### Context

Spec 00 §3 allows municipal installations to share **optional aggregated indicators** upwards to the hub. Tickets are anonymous but can still identify people in small units when combined (OQ-21). Pooled learning across units (OQ-8 take-up, OQ-16 vulnerability relationship, OQ-27 priors) would benefit from data from several municipalities, but only if privacy holds.

### Constraints already stated

- **Only aggregated, anonymised indicators** leave an installation; never tickets or per-request records.
- **Opt-in** per municipality, revocable, and visible to the municipality before anything is sent.
- Aggregation and minimum cell sizes follow the rules decided for OQ-21 (ADR 0010); nothing flows until OQ-21 is decided.

### Options to evaluate

1. **No upward flow** in the first versions.
2. **Manual export** of an aggregate file that the municipality reviews and sends.
3. **Automated push** of aggregates on a schedule, after the municipality opts in.
4. Privacy-enhancing techniques (for example differential-privacy noise on counts) on top of 2 or 3.

### Questions to answer before deciding

- Which indicators are useful to the hub (and to which paper), at which spatial and temporal aggregation?
- Minimum cell size and suppression rules (OQ-21), and how they interact with pooled learning (OQ-8, OQ-27).
- Legal basis and data-protection impact assessment (GDPR); who is controller and processor.
- Audit trail of what was sent and when.

### Decision

Not decided.

### Consequences

To be written. No indicator is sent upwards until Part B and ADR 0010 are accepted.
