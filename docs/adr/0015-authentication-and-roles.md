# 0015. Authentication and roles

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
- Related: Spec 00 §3 (Scenario owner and visibility, Deployment), OQ-21; ADR 0010, 0012

## Context

Scenarios have an **owner and visibility** (private, shared) (Spec 00 §3). Installations have their own users; the hub has its own. Tickets are entered by staff at facilities and must stay anonymous (AGENTS.md). The bootstrap has no authentication: all endpoints are open and the stack binds to `127.0.0.1` only.

## Options to evaluate

1. **Built-in accounts** in the backend (password hashing, sessions or tokens).
2. **External identity provider** via OpenID Connect (for example Keycloak, Apache-2.0, run as an extra container), so municipalities can connect their own directory.
3. **Reverse-proxy authentication** in front of the app, with roles passed in headers.

## Candidate roles (to confirm)

Analyst or researcher (scenarios, runs, results), facility staff (ticket entry only), municipal administrator (users, data package import, upward sharing opt-in, ADR 0014), hub operator (onboarding, package publishing), read-only viewer.

## Questions to answer before deciding

- Which roles are needed in each deployment role (ADR 0012)?
- Must ticket entry work on shared devices without personal accounts (QR flow, Paper 4 §4.1), and how does that interact with OQ-21?
- Audit logging requirements; session lifetime; password and MFA policy.
- Licence of any identity component (must be AGPL-compatible).

## Decision

**Accepted for v0.1, to be revisited: option 1, built-in local accounts** behind an
`IdentityProvider` interface (`backend/src/solidaritynode_backend/auth.py`), so OpenID Connect
can replace it later without changing routers.

- Passwords hashed with Argon2id (`argon2-cffi`, MIT). **Policy**: at least **12 characters**
  and not on a bundled list of common passwords (1,210 entries of 12+ characters from SecLists'
  NCSC list, MIT, `backend/src/solidaritynode_backend/resources/common_passwords.txt`; case is
  ignored); **no composition rules** (no forced digits or symbols). Applied wherever a password
  is set: user creation and change (API and Admin screen) and `make create-admin`. Existing
  hashes keep working.
- **Sign-in throttling** per username and per client address
  (`services/throttle.py`, table `login_throttle`, migration 0009): after failure *n* the next
  attempt for that username is refused for `1 s × 2^(n-1)` (at most 30 s); a client address is
  delayed the same way only from half its limit on (10 failures), so one person's typo does not
  delay colleagues behind the same office address; after
  5 failures for a username or 20 for an address within 15 minutes it is locked for 15 minutes
  (all configurable, `SOLIDARITYNODE_LOGIN_*`). While delayed or locked the password is not
  checked and the answer is a generic 429 with `Retry-After`; wrong passwords and unknown users
  get the same 401 "wrong username or password", so neither reveals which accounts exist.
  Usernames and addresses are stored only as SHA-256 hashes. A successful sign-in clears both.
  A refused (429) attempt is not counted and never extends a delay or lock, so a lock ends at the
  stated time.
- **Client address** (`services/throttle.py`, `client_address`): the TCP peer, unless the peer
  is a trusted proxy listed in `SOLIDARITYNODE_TRUSTED_PROXIES` (addresses or CIDR networks;
  default loopback and the private networks of the compose network). From a trusted proxy the
  backend takes `X-Real-IP`, or the nearest `X-Forwarded-For` entry that is not itself a proxy;
  headers from any other peer are ignored, so a client cannot choose its address. The bundled
  nginx overwrites both headers with the address it sees (uvicorn runs with
  `--no-proxy-headers`, so this is the only place headers are read). In production list only the
  reverse proxy and never publish the API port.
- **When the proxy cannot see the client.** Behind rootless Podman's port forwarder every
  browser reaches nginx from nginx's own address (found in UAT: all sign-ins came from
  `10.89.0.6`, so the per-address limit counted every user together and one person's mistakes
  locked out everyone). When the address a proxy reports is itself a trusted proxy address, the
  client address is **unknown**: only the per-username limit applies, and the backend logs a
  warning once. Failed tries for one username therefore never block another username there.
  Where client addresses are visible (Docker, rootful Podman, a production reverse proxy), the
  per-address limit applies as described above; on a shared office address it can still delay
  colleagues once that address reaches half its limit (10 failures).
- **Clearing locks.** An administrator clears sign-in delays and locks with
  `make clear-login-locks USERNAME=<name>` (one username) or `make clear-login-locks` (all
  usernames and addresses); see `docs/uat/README.md`.
- Opaque session token in an HttpOnly, SameSite=Strict cookie (`Secure` with
  `SOLIDARITYNODE_SESSION_COOKIE_SECURE=true`, **always** with `APP_ENV=production`: the
  settings, and so `make check-config` and every start, refuse production without it); only its SHA-256 is stored; lifetime
  `SOLIDARITYNODE_SESSION_HOURS`. Disabling a user or changing a password ends their sessions.
- Roles for v0.1: `viewer` (shared scenarios and their results), `analyst` (also creates, edits,
  runs and shares own scenarios), `admin` (also manages users and imports data packages). Every
  endpoint that reads or writes scenarios, runs, results, users or packages checks them.
- **What "private" means.** A private scenario, with its runs and results, is hidden from
  other analysts and from viewers, **not from administrators**: admins see, open, edit and run
  every scenario. This is deliberate. Admins operate the installation and have database access
  anyway, so hiding scenarios from them in the UI would only suggest a protection that does not
  exist. The UI says so: next to the visibility choice the analyst reads "Private: visible to
  you and to administrators", and an admin's Scenarios page lists other users' private
  scenarios in their own table, each labelled "private (owner X)". Tests:
  `test_private_means_hidden_from_other_analysts_and_viewers_not_admins` and
  `test_opening_runs_per_role` (backend).
- **At least one active admin.** Admins cannot demote or disable themselves, and the last active
  admin can never be demoted or disabled; the check locks the admin rows, so two admins demoting
  each other at the same moment cannot leave none.
- `make create-admin` creates the first administrator interactively. Two demo accounts are
  seeded only when `APP_ENV=development` (`docs/uat/README.md`).

**Why:** no extra container or identity component; enough for one installation on 127.0.0.1.

## Consequences

- Facility staff and hub operator roles are not implemented (ticket entry waits for ADR 0010).
- Throttling state lives in PostgreSQL, so it holds across API processes; a distributed attack
  from many addresses is limited only per username.

### Before the first pilot (not implemented now)

- **Email invitations and password reset**, with a **forced password change at first sign-in**
  (no admin ever knows a user's working password).
- **MFA with TOTP** (authenticator apps), at least for admins.
- **Audit log** of sign-ins (successful and failed), user changes, package imports and rollbacks,
  and exports: who, what, when, from which address; kept per OQ-21-compatible retention.
- **Provider support account**: an account for the service provider that is disabled by
  default, enabled by the municipality for a limited time, and fully audited.
- **Transfer of ownership** of a departing user's scenarios to another analyst, so disabling a
  user does not orphan shared work.
- **Onboarding guide for the municipal admin**: first admin, users and roles, package import
  and rollback, backups (ADR 0008), what the throttling and lock messages mean.

### Later

- **Single sign-on with OpenID Connect** behind the existing `IdentityProvider` interface.
- A **facility manager** role scoped to one facility (Paper 4: operational data per facility).
- **Per-facility device keys** for ticket entry on shared devices without personal accounts,
  designed together with ADR 0010 and OQ-21 (no ticket is stored until those are decided).
