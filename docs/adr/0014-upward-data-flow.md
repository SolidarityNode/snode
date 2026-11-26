# 0014. Upward data flow from municipalities to the hub

- Status: Proposed (Part A, facility corrections: proposal for v0.2, under review in PR #14; Part B, aggregated indicators: stub, needs a human decision)
- Date: 2026-11-24 (Part A: 2026-11-26)
- Related: Spec 00 §3 (Deployment), OQ-21, OQ-8, OQ-16, OQ-27; ADR 0006, 0010, 0012, 0013, 0015

Two kinds of data could travel from a municipal installation to the hub: **corrections of
facility data** (Part A, proposed for v0.2) and **aggregated indicators** from operation
(Part B, not decided). They have different privacy profiles and are decided separately.

## Part A: facility corrections submitted from a municipal installation (proposal for v0.2)

**Status of this part: Proposed, waiting for the maintainer's answers in PR #14.** Points
marked *(v0.2)* are simplifications to be accepted for v0.2 and revisited.

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

**Relation to Part B.** Facility corrections are reference data about organisations, not
operational data: the import already drops anything that looks like personal data
(`facility-import.md`). Part A therefore does **not** relax Part B: tickets, per-request records
and aggregated indicators still never leave an installation until Part B and ADR 0010 are
decided. It also keeps ADR 0012's rule: **every connection is opened by the installation**; the
hub never calls an installation and holds no credentials *for* it (it only keeps the hash of a
token the installation presents).

### A1. Connection

- The installation calls the hub API over **HTTPS**. The hub address is set **only in
  configuration** (`SOLIDARITYNODE_HUB_URL`), never from the UI, so a user cannot make the
  server call an arbitrary address (SSRF).
- With `APP_ENV=production` the settings refuse a plain `http://` URL except `localhost` /
  `127.0.0.1` (checked by `make check-config`, like the other production rules). Development
  allows `http` for the two local compose projects.
- The hub serves the installation API under its own prefix (for example `/hub/installation/…`),
  authenticated by the installation token (A2) in an `Authorization: Bearer` header, not by
  session cookies; the frontend proxy passes it through unchanged.

### A2. Trust between installations

- A hub administrator **registers** each installation (name, the one study area it serves) and
  **issues an installation token**: random (at least 256 bits), shown **once**, stored in the hub
  only as its SHA-256 (as sessions are, ADR 0015), and stored in the municipal `.env` as the
  secret `SOLIDARITYNODE_HUB_TOKEN` (never in git, never logged, never shown in the UI; the UI
  only says "token present: yes/no").
- **Scope** of a token: submit changes for the **core** municipalities of its study area only
  (not the buffer: a municipality does not correct its neighbours); read the status of **its
  own** submissions; list and download the packages of **its own** study area. Nothing else.
- **Revocation** takes effect at once. **Rotation**: issuing a new token revokes the old one at
  once *(v0.2; a grace period can come later)*. The hub records the last contact (time, client
  address as seen by its proxy, ADR 0015) per installation.
- Failed token checks are throttled like sign-ins (ADR 0015) and answered with one generic 401.

### A3. Offline fallback

- An installation without a network path to the hub exports a **submission file**: an archive
  with the same content as an online submission (A7: the **sanitised** rows and the changeset,
  never the original upload) and a `manifest.json` with SHA-256 checksums.
- The file carries the installation id and an **HMAC-SHA256 of its content keyed with the
  installation token**, so the hub can check which installation made it without a network call.
- A hub administrator uploads it; the hub treats it exactly as an online submission (same
  validation, same changeset, same status). Status then travels back only when the installation
  is next online, or by hand (the municipal admin can mark a submission "sent offline").

### A4. Lifecycle and status

```
draft → sent → received → rejected_by_validation
                        → pending_review → approved → published_in <version> → imported
                                         → rejected
```

- `draft`: saved locally, validated locally, not sent. `sent`: queued for the worker, or being
  retried (A5); the last error and next try are shown. `received`: the hub stored it (it returns
  its changeset id). `rejected_by_validation`: the hub's own validation found errors.
  `pending_review` → `approved` / `rejected` by a hub administrator, **with a comment** that is
  shown in the municipality. `published_in <version>`: a published package of the
  installation's study area contains the changeset (the manifest's `provenance` lists
  changeset ids). `imported`: the installation imported that version (or a later one).
- Every transition stores who (municipal user, or "hub" with the hub administrator's username)
  and when.

### A5. Synchronisation

- A **scheduled job in the worker** (`hub_sync`) sends queued submissions and polls the hub for
  status changes and new package versions, every `SOLIDARITYNODE_HUB_SYNC_SECONDS` (default
  300). The Submissions page asks for an extra sync while it is open (a "check now" that queues
  the job; it never calls the hub from the request handler).
- **Retries with exponential backoff** (for example 1 min, doubling, at most 1 h) while the hub
  is unreachable; the submission stays `sent`.
- **Idempotent resend:** every submission has a UUID chosen by the installation; the hub stores
  it, and a second send of the same UUID returns the existing changeset instead of creating
  another.
- This is ADR 0006's revisit trigger 3 (scheduled jobs) and 4 (retries of external calls).
  *(v0.2)*: the worker gets a small periodic tick that enqueues `hub_sync` when none is queued or
  running, on the existing PostgreSQL queue; procrastinate stays the candidate if scheduling
  grows.

### A6. New package versions

- The sync job lists the packages of the installation's study area. A newer version than the
  active one is shown to the **administrator** as "a new version is available" with its
  changelog. **Download** is on the administrator's request (a job), verifying the archive's
  SHA-256 against the hub's package record; the existing **preview and confirm** then applies. No
  automatic import.
- **Signing.** *(v0.2)*: checksums over TLS are enough because the download is made by the
  installation itself, from the hub address in its configuration, with its token, over HTTPS;
  the checksum comes over the same authenticated channel; and an administrator still previews
  and confirms every import. Signing (for example minisign or Sigstore, key held by the hub) is
  required before any **automatic** import, or for packages passed around outside the platform
  (ADR 0013 "Consequences" stays valid for manual files).

### A7. Privacy

- Validation runs **locally first**, with the **same validator code** as the hub, on the
  facilities of the installation's active package; personal-data columns and values are dropped
  **before anything leaves the municipality**. What is sent: the sanitised rows (template
  columns only), the computed changeset and the comment; **never the original file**. The hub
  validates again on receipt.
- Shared code: the parsing, personal-data and row checks are pure and can move to `core` or a
  backend module used by both roles; locating points needs PostGIS and stays in the backend,
  reading the hub's curated features in the hub and the active data version in the
  installation.
- The hub stores who submitted as "municipality X (installation Y, user Z)". User Z is a
  municipal employee: see decision 19.

### A8. Conflicts

- Each item of a submission records the **package version it was based on** and a fingerprint
  of the facility as that package had it. On receipt, the hub compares it with the facility's
  current state.
- If the hub changed the facility since (another changeset, a later version), the item is marked
  **conflict**, shown in the review with the three states (in the municipality's package, now in
  the hub, proposed); it is never overwritten silently. *(v0.2)*: the hub administrator must
  confirm each conflicting item explicitly, or reject the submission.

### A9. "Complete list" from a municipality

- Allowed: the municipal UI asks for the same confirmation as the hub (type the number of
  facilities that will be closed); the hub review shows the closures prominently and asks for
  the count again before approving.

### Consequences (Part A, if accepted)

- New settings in the municipal installation: `SOLIDARITYNODE_HUB_URL`,
  `SOLIDARITYNODE_HUB_TOKEN` (secret), `SOLIDARITYNODE_HUB_SYNC_SECONDS`.
- New tables: in the hub, installations and their token hashes, and the submission UUID on
  changesets; in the installation, submissions with their status history.
- ADR 0006 gains the periodic tick (A5); ADR 0012 and 0015 gain the installation token as a
  second kind of credential.
- Part B (aggregated indicators) is unchanged and still not decided.

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
