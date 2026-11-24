# 0015. Authentication and roles

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
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

Not decided.

## Consequences

To be written. Until decided, the stack must only listen on `127.0.0.1` and hold synthetic data.
