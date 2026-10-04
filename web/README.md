# web — dashboard

Vite + React 19 + TypeScript + Tailwind 4 + React Router + Recharts. FRONTEND
owns everything in here.

```bash
npm install
npm run dev        # http://localhost:3010
npm run build       # tsc -b && vite build
npm run lint
npm run test        # vitest run
```

The dev server proxies `/api`, `/health`, `/ready` and `/ws` to FastAPI on
`:8000` (see `vite.config.ts`), so nothing here ever needs a CORS workaround
or a hardcoded backend URL.

## What this is

The real dashboard: seven pages — Overview, Incident detail, Topology,
Approval, Regional risk, Cost and waste, and Savings report — behind a dark
232px sidebar. The backend isn't built yet, so every page reads from a mock
data layer (`src/api/mock/*`) through `src/api/client.ts`. Flip
`VITE_USE_MOCK=false` once the real API exists; no page or component needs
to change, only that one file.

```
src/
  api/client.ts      # typed functions; VITE_USE_MOCK switches mock ↔ real
  api/mock/*.ts       # sample data for all 7 screens
  api/types.ts        # Incident, Decision, Vote, Region, CostEstimate, …
  components/         # Card, Badge, KpiCard, Sidebar, Countdown, DataTable
  pages/              # Overview, Incident, Topology, Approval, Risk, Cost, Savings
```

## Deliberate choices worth keeping

- **Fonts are self-hosted, not a webfont request.** IBM Plex Sans/Mono ship
  via `@fontsource`, bundled at build time — zero network request for type,
  so it still works with WiFi off.
- **Colour is never the only signal.** Every status pairs its colour with a
  symbol and a word: `● Low`, `▲ Elevated`, `■ High`.
- **A missing value is not a zero.** A `Decision.terms` dict missing a key
  renders `n/a` (that term doesn't apply to this option); a missing metric
  renders `no data`. Neither case silently becomes `0` — see
  `src/lib/format.ts` and its tests.
- **Data is monospaced, prose is not.** Numbers, ids, and formulas use IBM
  Plex Mono via the `.tabular` class so they don't reflow on update.
- **"Sample data" is always visible** while `VITE_USE_MOCK` is on, so nobody
  mistakes mock numbers for real ones.
