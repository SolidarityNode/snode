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

- Passwords hashed with Argon2id (`argon2-cffi`, MIT); minimum 8 characters.
- Opaque session token in an HttpOnly, SameSite=Strict cookie (`Secure` with
  `SOLIDARITYNODE_SESSION_COOKIE_SECURE=true`); only its SHA-256 is stored; lifetime
  `SOLIDARITYNODE_SESSION_HOURS`. Disabling a user or changing a password ends their sessions.
- Roles for v0.1: `viewer` (shared scenarios and their results), `analyst` (also creates, edits,
  runs and shares own scenarios), `admin` (also manages users and imports data packages). Every
  endpoint that reads or writes scenarios, runs, results, users or packages checks them.
- `make create-admin` creates the first administrator interactively. Two demo accounts are
  seeded only when `APP_ENV=development` (`docs/uat/README.md`).

**Why:** no extra container or identity component; enough for one installation on 127.0.0.1.

## Consequences

- Facility staff and hub operator roles are not implemented (ticket entry waits for ADR 0010).
- No MFA, password policy beyond length, or audit log yet; revisit before any deployment beyond a
  local machine.
