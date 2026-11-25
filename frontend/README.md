# solidaritynode-frontend

React + TypeScript (strict) web UI, built with Vite and managed with pnpm.

```bash
pnpm install --frozen-lockfile
pnpm dev        # http://localhost:5173, proxies /api to http://localhost:8000
pnpm test       # Vitest
pnpm lint       # ESLint + Prettier check
pnpm typecheck
```

Screens: login, study area, scenarios, scenario editor, run, compare, admin, health. Maps with
Leaflet (ADR 0007). API types are generated from the backend OpenAPI schema
(`pnpm gen:api` or `make schemas`) into `src/api/schema.d.ts`. All text lives in
`src/i18n/en.json` and `el.json`. End-to-end test: `make test-e2e` (Playwright).
