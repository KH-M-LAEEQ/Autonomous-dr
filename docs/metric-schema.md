# Canonical metric schema — 20 signals + 5 reserve

**Frozen in Week 3.** The collector writes these from Week 3 onward, 24/7. Adding a
signal later means no history for it, so every model trained before that date can't use
it. Decide once, properly.

**The collector writes 25 fields. The canonical set is 20.** Signals 21–25 are collected
but not consumed by detectors, the dashboard, or `Φ`. They cost nothing to gather and
mean that if one turns out to matter in November, there are months of history behind it
instead of none. Promoting a reserve signal to canonical is an ADR, not a migration.

All signals are per-resource, per-tenant, per-region. Tags: `tenant`, `region`,
`resource_id`, `provider`.

---

## Compute (5)

| # | Name | Unit | AWS CloudWatch | Azure Monitor | GCP Cloud Monitoring |
|---|---|---|---|---|---|
| 1 | `cpu_percent` | 0–100 | `CPUUtilization` | `Percentage CPU` | `instance/cpu/utilization` |
| 2 | `memory_percent` | 0–100 | `mem_used_percent` (CW agent) | `Available Memory Bytes` → derive | `instance/memory/balloon/ram_used` (Ops Agent) |
| 3 | `disk_used_percent` | 0–100 | `disk_used_percent` (CW agent) | `OS Disk Used` | `instance/disk/percent_used` (Ops Agent) |
| 4 | `disk_io_ops` | ops/s | `EBSReadOps` + `EBSWriteOps` | `Disk Read Operations/Sec` + write | `instance/disk/read_ops_count` + write |
| 5 | `process_count` | count | CW agent `processes_total` | guest metrics | `processes/count_by_state` (Ops Agent) |

## Network (4)

| # | Name | Unit | AWS CloudWatch | Azure Monitor | GCP Cloud Monitoring |
|---|---|---|---|---|---|
| 6 | `net_in_bytes` | bytes/s | `NetworkIn` | `Network In Total` | `instance/network/received_bytes_count` |
| 7 | `net_out_bytes` | bytes/s | `NetworkOut` | `Network Out Total` | `instance/network/sent_bytes_count` |
| 8 | `net_packets_dropped` | count/s | `NetworkPacketsIn` delta | `Inbound Flows` delta | `instance/network/received_packets_count` delta |
| 9 | `active_connections` | count | ELB `ActiveConnectionCount` | `Connection Count` | `https/backend_request_count` (LB) |

## Service health (6)

| # | Name | Unit | AWS CloudWatch | Azure Monitor | GCP Cloud Monitoring |
|---|---|---|---|---|---|
| 10 | `request_rate` | req/s | ELB `RequestCount` | `Requests` | `https/request_count` |
| 11 | `error_rate_5xx` | 0–1 | `HTTPCode_Target_5XX` / `RequestCount` | `Http5xx` / `Requests` | `https/request_count` filtered `response_code_class=500` |
| 12 | `error_rate_4xx` | 0–1 | `HTTPCode_Target_4XX` / `RequestCount` | `Http4xx` / `Requests` | same, `response_code_class=400` |
| 13 | `latency_p50` | ms | `TargetResponseTime` p50 | `Response Time` p50 | `https/total_latencies` p50 |
| 14 | `latency_p95` | ms | `TargetResponseTime` p95 | `Response Time` p95 | `https/total_latencies` p95 |
| 15 | `latency_p99` | ms | `TargetResponseTime` p99 | `Response Time` p99 | `https/total_latencies` p99 |

## Availability (3)

| # | Name | Unit | AWS CloudWatch | Azure Monitor | GCP Cloud Monitoring |
|---|---|---|---|---|---|
| 16 | `health_check_pass` | 0 or 1 | Route 53 `HealthCheckStatus` | `Probe Status` | `uptime_check/check_passed` |
| 17 | `healthy_target_count` | count | ELB `HealthyHostCount` | `Healthy Host Count` | `instance_group/size` healthy filter |
| 18 | `uptime_seconds` | seconds | derive from instance state | derive | `instance/uptime` |

## Saturation (2)

| # | Name | Unit | AWS CloudWatch | Azure Monitor | GCP Cloud Monitoring |
|---|---|---|---|---|---|
| 19 | `queue_depth` | count | SQS `ApproximateNumberOfMessagesVisible` | `Queue Length` | Pub/Sub `subscription/num_undelivered_messages` |
| 20 | `throttle_count` | count/s | `ThrottledRequests` | `Throttled Requests` | `serviceruntime/quota/exceeded` |

## Reserve — collected, not canonical (5)

Written to InfluxDB alongside the 20. Nothing reads them yet.

| # | Name | Unit | Why it's here |
|---|---|---|---|
| 21 | `replication_lag_seconds` | seconds | **The most likely promotion.** Nothing in 1–20 answers "is the standby current?" — and promoting a stale replica is the worst failure this system can cause. Canonical from the moment a Tier 3 action exists. |
| 22 | `tcp_retransmit_rate` | 0–1 | Network degradation shows here before it shows in latency percentiles. Cheap early signal. |
| 23 | `swap_used_percent` | 0–100 | Memory pressure that `memory_percent` misses — a host can look fine on RAM while thrashing. |
| 24 | `open_file_descriptors` | count | Classic slow-leak failure. Flat for days, then a hard wall. Needs long history to be useful, which is exactly why it's collected now. |
| 25 | `gc_pause_ms` | ms | Application-layer stalls invisible to infrastructure metrics. Testbed only — most resources will be null. |

**Absent is fine. Don't zero-fill.** A null means "not applicable to this resource
type", which is different from zero, and the distinction matters once these feed
anything.

---

## Why these

**Covers the four golden signals** — latency (13–15), traffic (10), errors (11–12),
saturation (1–5, 19–20). Anything a fault does shows up in at least one.

**Every signal is per-resource.** Required, because Li's `Φ_m` (`docs/formulas.md` §1)
scores individual nodes from their historical performance. A cluster-wide-only metric
can't feed it.

**Every signal exists on all three providers.** Anything available on only one or two was
left out — the normalisation layer can't invent data. GCP arrives in Week 21, so its
column is written now to confirm the set survives a third provider rather than being
retrofitted.

**Three latency percentiles, not a mean.** Week 28 reports p50/p95/p99 and detection
delay is reported as a distribution. Collecting only the mean makes that impossible
retroactively.

**Rates, not counters, for errors.** `error_rate_5xx` as a ratio is comparable across
resources of different sizes. A raw 5xx count is not.

## Notes before freezing

- **2, 3, 5** need a guest agent on every provider — CloudWatch agent on AWS, guest
  metrics on Azure, Ops Agent on GCP. Not available from base instance metrics alone.
  Verify in Week 7 or drop them.
- **9, 10–15, 17** are load-balancer metrics. A bare instance has none of them on any
  provider. Decide in Week 7 whether the free-tier setup includes an ALB / Application
  Gateway / GCLB, or these stay simulator- and testbed-only.
- **GCP naming.** Cloud Monitoring prefixes every metric type with
  `compute.googleapis.com/` or `loadbalancing.googleapis.com/`. Short forms are used
  above; the adapter uses full types.
- **GCP counters vs gauges.** 6, 7, 8 are cumulative counters on GCP but gauges on AWS
  and Azure. The GCP adapter differences them before writing — otherwise the same
  canonical field holds two different kinds of number depending on provider, which
  silently breaks every detector trained on it.
- **19–20** may be empty for most resources. Absent is fine; the detector handles nulls.
  Don't zero-fill.
- The Week 8 testbed (Online Boutique / Sock Shop + OpenTelemetry) produces 10–15
  natively, which is where most training data comes from.

## Promotion path for 21

`replication_lag_seconds` is the one most likely to become canonical. Tier 3 actions
(full DR promotion) land in Week 17. At that point the decision engine needs to know
whether the target is current before promoting it — most likely as a hard gate in the
same shape as the budget cap, not as a weighted term.

Collecting it from Week 3 means the gate can be built in Week 17 against real history
rather than starting from zero.

## Φ subset

Not all 20 feed the capability score. Li's `Θ` set is service-quality indicators —
availability, latency, loss. Suggested subset for `Φ_m`:

```
health_check_pass, uptime_seconds, latency_p95, error_rate_5xx, net_packets_dropped
```

Entropy weights (Eq. 3) are computed over these five. The remaining 15 are detector
inputs only.
