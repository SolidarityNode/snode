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
  attempt for that username or address is refused for `1 s × 2^(n-1)` (at most 30 s); after
  5 failures for a username or 20 for an address within 15 minutes it is locked for 15 minutes
  (all configurable, `SOLIDARITYNODE_LOGIN_*`). While delayed or locked the password is not
  checked and the answer is a generic 429 with `Retry-After`; wrong passwords and unknown users
  get the same 401 "wrong username or password", so neither reveals which accounts exist.
  Usernames and addresses are stored only as SHA-256 hashes. A successful sign-in clears both.
  The client address comes from nginx, which overwrites `X-Forwarded-For`; uvicorn trusts it
  only from `FORWARDED_ALLOW_IPS` (the compose network by default).
- Opaque session token in an HttpOnly, SameSite=Strict cookie (`Secure` with
  `SOLIDARITYNODE_SESSION_COOKIE_SECURE=true`, **always** with `APP_ENV=production`: the
  settings, and so `make check-config` and every start, refuse production without it); only its SHA-256 is stored; lifetime
  `SOLIDARITYNODE_SESSION_HOURS`. Disabling a user or changing a password ends their sessions.
- Roles for v0.1: `viewer` (shared scenarios and their results), `analyst` (also creates, edits,
  runs and shares own scenarios), `admin` (also manages users and imports data packages). Every
  endpoint that reads or writes scenarios, runs, results, users or packages checks them.
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
