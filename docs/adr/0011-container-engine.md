# 0011. Container engine (Podman default, Docker supported)

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: AGENTS.md "Stack"; `Makefile`, `compose.yaml`

## Context

Contributors work on Linux, macOS and Windows/WSL2. AGENTS.md sets Podman (rootless) as the default engine and requires Docker to keep working. The bootstrap implements this: the Makefile defines `CONTAINER_ENGINE ?= podman` and `COMPOSE ?= podman compose`; images use fully qualified names; ports are non-privileged; no bind mounts; healthchecks live in `compose.yaml` because Podman's OCI image format ignores `HEALTHCHECK`; CI builds images with both engines.

## Options to evaluate

1. **Podman default, Docker supported** (current implementation).
2. Docker default, Podman supported.
3. Podman only.

## Questions to answer before deciding

- Confirm the current implementation as the accepted decision.
- Which compose provider is supported for Podman (`podman compose` delegating to `podman-compose` or `docker-compose`)? Verified locally with podman-compose 1.5.0.
- Should CI also run the full stack (`make up`) with both engines, not only image builds?

## Decision

Not decided.

## Consequences

To be written with the decision.
