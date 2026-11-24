# AGENTS.md (frontend)

Applies to files under frontend/, in addition to the root AGENTS.md. If the two conflict, the root wins; report the conflict.

Explanations and examples: [docs/conventions/frontend.md](../docs/conventions/frontend.md).

## Rules

- No scientific or modelling logic in the frontend. All computation happens in `core` and reaches the UI through the backend API; the frontend only displays.
- Use one API client, generated from the backend OpenAPI schema or typed to match it. No hand-written duplicate types.
- Always show uncertainty (interval, distribution or probability), never a bare number.
- Visibly mark results from the diagnostic model, units with an edge-effect warning, and features of `estimated` or `open_data` quality.
- Accessibility: label every control, support keyboard navigation, use colour scales readable by colour-blind users, and give text alternatives for map information where practical.
- Route all user-facing text through translation files (Greek and English). No hard-coded strings in components.
- Use the map library and other major libraries only as decided in ADRs (`docs/adr/`).
- Tests: component tests with Vitest and Testing Library; main user flows with Playwright.
