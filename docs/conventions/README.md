# Conventions

Human-readable versions of the area rules. The rules themselves live in `AGENTS.md` files, which every coding agent and every contributor reads:

| Area | Rules (short, for agents) | Explanations (for humans) |
| --- | --- | --- |
| Whole repository | [`AGENTS.md`](../../AGENTS.md) | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) |
| `core/` | [`core/AGENTS.md`](../../core/AGENTS.md) | [`core.md`](core.md) |
| `backend/` | [`backend/AGENTS.md`](../../backend/AGENTS.md) | [`backend.md`](backend.md) |
| `frontend/` | [`frontend/AGENTS.md`](../../frontend/AGENTS.md) | [`frontend.md`](frontend.md) |
| `data-processing/` | [`data-processing/AGENTS.md`](../../data-processing/AGENTS.md) | [`data-processing.md`](data-processing.md) |

The root `AGENTS.md` always applies; an area file adds rules for its folder. If the two conflict, the root wins and the conflict is reported as an issue.

`CLAUDE.md` files are only bridges for Claude Code (they import the `AGENTS.md` next to them) and never contain rules.

To propose a rule change, see "Maintaining these instructions" in the root [`AGENTS.md`](../../AGENTS.md) and "Changing the rules" in [`CONTRIBUTING.md`](../../CONTRIBUTING.md). Every rule here has the same wording as in its `AGENTS.md`, plus a one-line reason and, where useful, an example.
