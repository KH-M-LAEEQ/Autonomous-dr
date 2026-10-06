# docs/metrics.md vs origin/add-metric-schema's docs/metric-schema.md

Not merged. Both describe "the canonical metric schema" but disagree enough
that reconciling them needs a conversation with Mahnoor, not a file merge.
`docs/metrics.md` lives on `feat/backend/week3-4-collector-detector`;
`docs/metric-schema.md` lives only on `origin/add-metric-schema` (unmerged).

## Scope

- **Mine**: exactly 20 signals. Nothing collected beyond the canonical set.
- **Theirs**: 20 canonical + 5 "reserve" signals (`replication_lag_seconds`,
  `tcp_retransmit_rate`, `swap_used_percent`, `open_file_descriptors`,
  `gc_pause_ms`) — collected from day one, consumed by nothing yet, with an
  explicit promotion path for `replication_lag_seconds`.

## Naming convention

- **Mine**: unit is baked into the name (`cpu_pct`, `network_in_bytes_per_s`,
  `latency_p50_ms`).
- **Theirs**: short name, unit in a separate column (`cpu_percent`,
  `net_in_bytes`, `latency_p50`).

## Signals that are the same concept, different name/unit

| Concept | Mine | Theirs |
| --- | --- | --- |
| CPU | `cpu_pct` (%) | `cpu_percent` (0-100) |
| Memory | `memory_pct` (%) | `memory_percent` (0-100) |
| Disk used | `disk_used_pct` (%) | `disk_used_percent` (0-100) |
| Disk I/O | `disk_read_bytes_per_s` + `disk_write_bytes_per_s` (2 signals, bytes/s) | `disk_io_ops` (1 signal, ops/s — combines read+write, different unit kind entirely) |
| Network in | `network_in_bytes_per_s` | `net_in_bytes` (same unit, shorter name) |
| Network out | `network_out_bytes_per_s` | `net_out_bytes` |
| Request rate | `request_rate_per_s` | `request_rate` |
| Errors | `error_rate_pct` (generic, %) **plus** `http_5xx_rate_pct` / `http_4xx_rate_pct` (3 signals total, %) | `error_rate_5xx` / `error_rate_4xx` only (2 signals, **0-1 fraction**, not %) |
| Latency percentiles | `latency_p50_ms` / `p95_ms` / `p99_ms` | `latency_p50` / `p95` / `p99` (same concept, unit column says ms) |

## Exact name matches (no conflict)

`active_connections`, `queue_depth` — identical names in both.

## Signals only I have

`db_connections_used`, `db_query_latency_p95_ms`, `cache_hit_rate_pct`,
`uptime_pct`. No database- or cache-specific signal in theirs at all.

## Signals only they have

`process_count`, `net_packets_dropped`, `health_check_pass` (0/1),
`healthy_target_count`, `uptime_seconds` (duration, not a health %),
`throttle_count`.

## Tag key mismatch

Mine (via `core/collector.py`'s actual `influx.write_metrics` call) tags
points with `tenant_id`, `region`, `resource_id`, `provider`, `kind`,
`health_state`. Theirs documents the tag set as `tenant`, `region`,
`resource_id`, `provider` — note **`tenant` vs `tenant_id`** as the literal
tag key, not just a documentation wording difference.

## Φ (capability score) subset

Theirs defines which 5 of the 20 feed `Φ_m` (entropy-weighted):
`health_check_pass, uptime_seconds, latency_p95, error_rate_5xx,
net_packets_dropped`. Mine doesn't define a Φ subset at all — and three of
theirs's five chosen signals (`health_check_pass`, `uptime_seconds`,
`net_packets_dropped`) don't exist in my 20. This is the piece most worth
resolving first: `web/src/api/types.ts`'s `TermKey` already has an `ability`
term (meant to carry `Φ`), so something upstream of the frontend needs to
agree on which signals actually compute it.

## Provider metric-name mapping

Theirs includes a full AWS CloudWatch / Azure Monitor / GCP Cloud Monitoring
column per signal. Mine only says this mapping happens in the Week 9
normalisation layer, without naming the actual provider metrics.

## "Don't zero-fill" — same rule, and a real implementation gap

Both docs state the same principle in different words: mine says a
provider's `0.0` for a signal it has no concept of means "not applicable,
not an anomaly"; theirs says to leave such a signal **null/absent**, never
zero-filled. Worth flagging alongside the docs diff: `core/providers/
simulated.py`'s `_generate_signals` currently returns a real `0.0` for every
one of the 20 canonical signals for every resource (e.g. `cache_hit_rate_pct`
for a non-cache resource comes from a `(0.0, 0.0, 100.0)` baseline), which is
a literal zero-fill — contradicting both docs' stated rule, not just
disagreeing with one of them.
