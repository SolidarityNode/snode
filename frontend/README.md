# solidaritynode-frontend

React + TypeScript (strict) web UI, built with Vite and managed with pnpm.

```bash
pnpm install --frozen-lockfile
pnpm dev        # http://localhost:5173, proxies /api to http://localhost:8000
pnpm test       # Vitest
pnpm lint       # ESLint + Prettier check
pnpm typecheck
```

At this stage: a layout, routing, a page that calls `/health`, and a typed API client
(`src/api/client.ts`). No map library yet (ADR 0007).
