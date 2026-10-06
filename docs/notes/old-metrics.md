> **REPLACED. Do not use.** This was one of two competing metric lists. The
> project settled on `docs/metric-schema.md` (20 canonical + 5 reserve signals),
> which is what `core/signals.py` now implements. This file is kept only so the
> reasoning behind the earlier selection stays on the record, and because
> `ml/datasets/v1`-`v3` were generated against these names and units.
>
> Differences between the two lists are tabulated in
> `docs/notes/metric-list-comparison.md`.

# Metric schema — the 20 canonical signals

Week 3, AI role. `core/signals.py` is the source of truth; this file is the
rationale. Per the build plan: "changing this later invalidates your
dataset, so decide it once, properly."

## The list

| # | Signal | Unit | Why it's in the 20 |
| - | --- | --- | --- |
| 1 | `cpu_pct` | % | The baseline resource-exhaustion signal every provider exposes natively. |
| 2 | `memory_pct` | % | Same — OOM-style degradation shows here before CPU. |
| 3 | `disk_used_pct` | % | Slow-burn failure mode (log growth, disk fill) that CPU/memory miss entirely. |
| 4 | `disk_read_bytes_per_s` | bytes/s | I/O-bound degradation (DB-heavy services) looks like neither CPU nor memory pressure. |
| 5 | `disk_write_bytes_per_s` | bytes/s | Paired with read; write-heavy faults (e.g. runaway logging) are a distinct failure shape. |
| 6 | `network_in_bytes_per_s` | bytes/s | Traffic-shape anomalies (DDoS-like spikes, stalled upstream) precede request-level symptoms. |
| 7 | `network_out_bytes_per_s` | bytes/s | Egress collapse is a distinct, detectable failure (e.g. downstream dependency down). |
| 8 | `request_rate_per_s` | req/s | Load context — the denominator every other rate-based signal needs to mean anything. |
| 9 | `error_rate_pct` | % | The single most direct user-facing health signal. |
| 10 | `latency_p50_ms` | ms | Typical-case recovery-time input to `U(c,l,m)`'s `l` term. |
| 11 | `latency_p95_ms` | ms | Tail latency degrades long before p50 does — earlier warning. |
| 12 | `latency_p99_ms` | ms | Catches the failure modes p95 still misses (a thundering-herd minority of requests). |
| 13 | `active_connections` | count | Saturation signal independent of CPU/memory — thread-pool/connection-pool exhaustion. |
| 14 | `queue_depth` | count | Backpressure building up is detectable before anything downstream notices. |
| 15 | `http_5xx_rate_pct` | % | Server-side failure, separated from 4xx so client-error noise doesn't mask it. |
| 16 | `http_4xx_rate_pct` | % | Client-side failure (bad deploys, auth breakage) is a different root cause than 5xx. |
| 17 | `db_connections_used` | count | The most common real-world cascade trigger (pool exhaustion) in multi-tier services. |
| 18 | `db_query_latency_p95_ms` | ms | Separates "the app is slow" from "the database is slow" for the explanation engine. |
| 19 | `cache_hit_rate_pct` | % | A collapsing hit rate is a leading indicator of latency/DB-load incidents, not just a symptom. |
| 20 | `uptime_pct` | % | The ground-truth health signal underlying everything else; also the input to the savings model (Week 23). |

## Rules

- Every `CloudProvider.get_health(resource_id).signals` dict uses exactly
  these 20 keys (a provider may report `0.0` for a signal it genuinely has no
  concept of — `0.0` there means "not applicable", so detectors must treat a
  provider's always-zero signal as a non-feature, not an anomaly magnet).
- `MetricWindow.values` keys are the same 20 strings.
- AWS CloudWatch / Azure Monitor native metric names are mapped **onto** this
  list in the Week 9 normalisation layer. No provider-specific key is ever
  added to `MetricWindow` or `HealthReport.signals` — that is what makes the
  benchmark harness (Week 10) and the cross-provider dashboard (Week 9) valid
  comparisons instead of apples-to-oranges.
- This list is frozen the same way the five interfaces are: changing it after
  the collector has accumulated data is a dataset-breaking change, not a
  refactor. Treat it with the same discipline (ADR if it must change).
