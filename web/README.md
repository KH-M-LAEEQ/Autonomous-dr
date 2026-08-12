# web — dashboard

Vite + React 19 + TypeScript + Tailwind 4. FRONTEND owns everything in here.

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api`, `/health`, `/ready` and `/ws` to FastAPI on :8000
(see `vite.config.ts`), so nothing here ever needs a CORS workaround or a
hardcoded backend URL.

## What this is, and what it is not

This is the Week 1 **stack proof**, not the dashboard. It answers one question
for a teammate who just cloned the repo: *is my whole stack actually wired up?*
It shows API reachability, Postgres and InfluxDB readiness, which
implementations of the frozen interfaces are live, and the WebSocket envelope
arriving.

The real dashboard starts in Week 3 (shell, routing, theme, empty states) and
grows every week after. Replace this page then — do not build on top of it out
of politeness.

## Deliberate choices worth keeping

- **No webfonts.** System font stack for prose, system mono for data. Zero
  network requests for type, which matters at Week 35 when you rehearse the demo
  with WiFi switched off.
- **Colour is semantic, not decorative.** `--color-ok / --color-warn /
  --color-down` in `src/index.css` are the only status colours. If a component
  invents a fourth, that is a bug.
- **Data is monospaced, prose is not.** Numbers that change every 10 seconds
  must not reflow the layout.
