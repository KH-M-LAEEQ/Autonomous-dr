# Frontend endpoints the backend doesn't serve yet

`web/src/api/client.ts` calls 8 real-mode paths, all under `/api/v1/`
(see `vite.config.ts`'s proxy). This is a gap list, not a build plan --
nothing here is implemented by this doc.

Backend state referenced below is current as of this repo's two active
branches: `main` (health, a `/api/v1/resources` stub, a `/api/v1/incidents`
stub, `/api/v1/actions` + `/api/v1/faults` stubs) and
`feat/backend/week3-4-collector-detector` (adds a real provider registry,
collector, incident state machine, and threshold detector -- none of which
are exposed through these 7 pages' endpoints yet).

## Overview page -- `GET /api/v1/overview`

No router exists. Needs, per `OverviewData` (`web/src/api/types.ts`):
- `kpis`: KPI summaries (no aggregation code anywhere yet)
- `recoveryLatency`: a time series (no table/query backs this)
- `incidents`: incident summaries -- closest existing data is
  `core.incidents.list_incidents`, but that returns raw rows
  (id/tenant_id/resource_id/state/opened_at/closed_at), not the
  title/provider/severity shape `IncidentSummary` needs
- `cloudStatus`: per-provider up/down -- nothing reads `enabled_providers()`
  and summarizes health today
- `activity`: an activity feed -- `core.repo.audit.list_for_verification`
  is the nearest thing (hash-chain audit log) but isn't exposed via API
  and isn't shaped as an activity feed

## Incident detail page -- `GET /api/v1/incidents/{id}`

Partially exists: `api/routers/incidents.py` on the backend branch returns
basic row fields only (id, tenant_id, resource_id, state, opened_at,
closed_at, trigger_detection_id), via `core.incidents.get_incident`. Its
own docstring says explanation/decision/votes/actions "join in once those
tables have writers (Week 5+)."

Still missing, per `IncidentDetail`:
- `title`, `severity`, `provider` -- not derived anywhere
- `timeline`: no timeline-building code
- `explanation`: `Explanation` (ADR-0009 shape: text/citations/engine/
  unsupported) -- nothing produces this yet
- `votes`: no votes table writer or reader
- `decision`: `Decision` with `weights`, `formulaVersion`, and
  `ScoredOption[]` (`terms`, `utility`, `chosen`) -- this is the
  formula-contract work (`core/decision/utility.py`, ADR-0011), not yet
  on any branch in this repo
- `budgetCheck`: no budget-cap check exists
- `auditEntries`: the hash-chained audit log exists
  (`core.repo.audit`, `core.audit.hash_chain`) but has no read endpoint
- `canRollBack`: no rollback concept exists yet

## Topology page -- `GET /api/v1/topology`

No router exists. Needs `services`/`edges` (a dependency graph),
`failedServiceId`, `blastRadius`, `predictedNextAtRisk`. The merged
migration's `graph`/`snapshot_id` columns (see `infra/migrations/`) suggest
a graph table is planned, but nothing reads or writes it, and no endpoint
shapes it into `TopologyData`.

## Approval page (Tier 3) -- `GET /api/v1/approvals/{id}`

No router exists. Needs `ApprovalRequest`: proposed action, cost estimate,
budget remaining, ETA, undo window, dry-run plan, countdown, fallback tier.
Depends on the same unbuilt `Decision`/budget-gate work as the incident
detail page's `decision` and `budgetCheck` fields.

## Regional risk page -- `GET /api/v1/risk/regions`

No router exists. Needs `RegionRisk[]` (score, breakdown, signals) and a
`RiskWeightPolicy`. The merged migration adds `risk_signals.source_type`
and `source_url`, so a signals table is planned, but there's no writer,
no reader, and no endpoint.

## Cost and waste page -- `GET /api/v1/cost`

No router exists. Needs spend/cap totals, `CostEstimateRow[]`,
`PriceComparisonRow[]`, `UnusedResource[]`. `CloudProvider.estimate_cost`
exists per-action (`SimulatedProvider`'s static price table), but nothing
aggregates it into this shape, and there's no idle-resource detection.

## Savings report page -- `GET /api/v1/savings`

No router exists. Needs `SavingsEntry[]` (downtime avoided / action cost /
overhead / net saving per incident) and a `SensitivityPoint[]` series.
Nothing computes downtime-avoided or overhead anywhere in the backend.

## Tenant info (app shell) -- `GET /api/v1/tenant`

No router exists. Needs `name` and `budgetCapUsd` for one tenant.
`core.repo.tenants.list_active_tenant_ids` only returns ids -- there's no
per-tenant detail read and no endpoint.
