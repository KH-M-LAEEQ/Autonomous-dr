# Metric list: `docs/metrics.md` vs `docs/metric-schema.md`, side by side

**No decision is made in this file.** It exists so the 20 canonical signals can
be chosen from one table instead of two documents. Choosing is yours.

Sources compared:

| Column | File | Lives on | Ref |
| --- | --- | --- | --- |
| **A** | `docs/metrics.md` | `feat/backend/week3-4-collector-detector` (and this branch) | `74bb4b5`, 2026-10-06 |
| **B** | `docs/metric-schema.md` | `origin/add-metric-schema` only — **not merged** | `2911117`, 2026-08-30 |

Totals: **A = 20 signals.** **B = 20 canonical + 5 reserve** (reserve is
collected but deliberately not canonical, so B writes 25 fields).

`core/signals.py` currently implements column A exactly — it is the only one of
the two that is wired to running code today (`SimulatedProvider._generate_signals`,
`CloudProvider.get_health`, `MetricWindow.values`).

## The table

"Unit" is reproduced as each file states it. A dash means that file has no signal
for the concept.

| # | Concept | A: `metrics.md` name | A unit | B: `metric-schema.md` name | B unit | Present in |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | CPU utilisation | `cpu_pct` | % | `cpu_percent` | 0–100 | **both** |
| 2 | Memory utilisation | `memory_pct` | % | `memory_percent` | 0–100 | **both** |
| 3 | Disk space used | `disk_used_pct` | % | `disk_used_percent` | 0–100 | **both** |
| 4 | Disk read throughput | `disk_read_bytes_per_s` | bytes/s | — | — | A only |
| 5 | Disk write throughput | `disk_write_bytes_per_s` | bytes/s | — | — | A only |
| 6 | Disk I/O operations | — | — | `disk_io_ops` | ops/s | B only |
| 7 | Network in | `network_in_bytes_per_s` | bytes/s | `net_in_bytes` | bytes/s | **both** |
| 8 | Network out | `network_out_bytes_per_s` | bytes/s | `net_out_bytes` | bytes/s | **both** |
| 9 | Packets dropped | — | — | `net_packets_dropped` | count/s | B only |
| 10 | Active connections | `active_connections` | count | `active_connections` | count | **both — identical name** |
| 11 | Request rate | `request_rate_per_s` | req/s | `request_rate` | req/s | **both** |
| 12 | Error rate (all errors) | `error_rate_pct` | % | — | — | A only |
| 13 | 5xx error rate | `http_5xx_rate_pct` | % | `error_rate_5xx` | **0–1** | **both — unit differs** |
| 14 | 4xx error rate | `http_4xx_rate_pct` | % | `error_rate_4xx` | **0–1** | **both — unit differs** |
| 15 | Latency p50 | `latency_p50_ms` | ms | `latency_p50` | ms | **both** |
| 16 | Latency p95 | `latency_p95_ms` | ms | `latency_p95` | ms | **both** |
| 17 | Latency p99 | `latency_p99_ms` | ms | `latency_p99` | ms | **both** |
| 18 | Queue depth | `queue_depth` | count | `queue_depth` | count | **both — identical name** |
| 19 | Throttling | — | — | `throttle_count` | count/s | B only |
| 20 | Process count | — | — | `process_count` | count | B only |
| 21 | Health check result | — | — | `health_check_pass` | 0 or 1 | B only |
| 22 | Healthy target count | — | — | `healthy_target_count` | count | B only |
| 23 | Uptime / availability | `uptime_pct` | % | `uptime_seconds` | **seconds** | **both — unit kind differs** |
| 24 | DB connections in use | `db_connections_used` | count | — | — | A only |
| 25 | DB query latency p95 | `db_query_latency_p95_ms` | ms | — | — | A only |
| 26 | Cache hit rate | `cache_hit_rate_pct` | % | — | — | A only |
| 27 | Replication lag | — | — | `replication_lag_seconds` | seconds | B only (**reserve**) |
| 28 | TCP retransmit rate | — | — | `tcp_retransmit_rate` | 0–1 | B only (**reserve**) |
| 29 | Swap used | — | — | `swap_used_percent` | 0–100 | B only (**reserve**) |
| 30 | Open file descriptors | — | — | `open_file_descriptors` | count | B only (**reserve**) |
| 31 | GC pause | — | — | `gc_pause_ms` | ms | B only (**reserve**) |

Row counts: A fills 20 rows (1,2,3,4,5,7,8,10,11,12,13,14,15,16,17,18,23,24,25,26).
B fills 20 canonical rows (1,2,3,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23)
plus 5 reserve (27–31).

## Things in the table that are not just a rename

These are the rows where picking "either name" is not enough, because the two
files disagree about the *number* or the *kind*:

- **Rows 4+5 vs 6.** A splits disk I/O into read and write **throughput**
  (bytes/s, 2 signals); B has a single **operation count** (`disk_io_ops`,
  ops/s, 1 signal). Not a renaming — different quantity, different unit, and 2
  slots vs 1.
- **Rows 13+14.** Same concept, but A is a **percentage** (0–100) and B is a
  **fraction** (0–1). A 100× difference that would silently corrupt any model
  trained across both conventions.
- **Row 12.** A has a generic `error_rate_pct` on top of its 5xx/4xx split, so A
  spends 3 slots on errors where B spends 2.
- **Row 23.** A's `uptime_pct` is a ratio; B's `uptime_seconds` is a duration.
  Same concept name, not interchangeable values.
- **Naming convention.** A puts the unit in the signal name (`cpu_pct`,
  `latency_p50_ms`); B keeps names short and carries the unit in a separate
  column (`cpu_percent`, `latency_p50`).

## Two things only one file supplies

Neither is a signal, but both affect which 20 you pick:

- **B has a provider mapping.** Every B signal has an AWS CloudWatch / Azure
  Monitor / GCP Cloud Monitoring column. A says this mapping happens in the
  Week 9 normalisation layer but does not name the provider metrics. B also
  flags that its rows 2, 3, 5 need a guest agent on all three providers, and
  that rows 9, 10–15, 17 are load-balancer metrics a bare instance does not
  have.
- **B defines the `Φ` subset.** B names the 5 signals that feed the capability
  score: `health_check_pass`, `uptime_seconds`, `latency_p95`, `error_rate_5xx`,
  `net_packets_dropped`. Three of those five (rows 21, 23-as-seconds, 9) do not
  exist in A at all. A defines no `Φ` subset. Worth knowing before you choose,
  because `web/src/api/types.ts` already ships an `ability` term key meant to
  carry `Φ`.

## Related

`docs/notes/metrics-diff.md` is the earlier prose summary of the same two files
(tag keys, zero-fill rule, promotion path). This file supersedes its signal-by-signal
section; the prose notes there still apply.
