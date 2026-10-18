# Robust-scaling floor -- design v2 (PB-14 follow-up)

> **Written before any v2 result was seen.** v1 remains the official v6
> result; v2 is a labelled sensitivity analysis.

## Why

The v1 scaling diagnostic (`docs/notes/lstm-design.md`, "Outcome" section)
found `error_rate_5xx_mean` and `error_rate_5xx_std` -- raw training IQR
0.000533 and 0.000342 on `sim-web-1` -- responsible for **99.7% of LSTM
validation loss**. Neither IQR is exactly zero, so v1's `if iqr > 0: spread
= iqr` branch takes it as the divisor verbatim: a near-zero-but-positive
IQR on a bounded signal produces scaled values over 1700, swamping every
other feature's contribution to a summed squared error.

## Rule (fixed, applied mechanically)

`spread = max(spread_v1, floor)`, where `floor` is 1% of the signal's
*documented* range in `docs/metric-schema.md`, for bounded signals only:

- Error rates (documented range `0-1`) -> floor `0.01`.
- CPU / memory / disk percent (documented range `0-100`) -> floor `1.0`.
- Every other signal -- no documented fixed range (latency is `ms`, bytes
  and counts are unbounded) -- gets **no floor**: v1 behaviour, unchanged.

Window features inherit their signal's floor: both `error_rate_5xx_mean`
and `error_rate_5xx_std` use `0.01`, same as the raw signal.

## All 19 detector signals

| Signal | Unit | Documented range | Floor |
|---|---|---|---|
| `cpu_percent` | % | 0-100 | 1.0 |
| `memory_percent` | % | 0-100 | 1.0 |
| `disk_used_percent` | % | 0-100 | 1.0 |
| `disk_io_ops` | ops/s | none | none |
| `process_count` | count | none | none |
| `net_in_bytes` | bytes/s | none | none |
| `net_out_bytes` | bytes/s | none | none |
| `net_packets_dropped` | count/s | none | none |
| `active_connections` | count | none | none |
| `request_rate` | req/s | none | none |
| `error_rate_5xx` | fraction | 0-1 | 0.01 |
| `error_rate_4xx` | fraction | 0-1 | 0.01 |
| `latency_p50` | ms | none | none |
| `latency_p95` | ms | none | none |
| `latency_p99` | ms | none | none |
| `health_check_pass` | 0 or 1 | none (binary indicator, not an error rate or a cpu/mem/disk percent) | none |
| `healthy_target_count` | count | none | none |
| `queue_depth` | count | none | none |
| `throttle_count` | count/s | none | none |

5 of 19 signals get a floor; 14 are unchanged from v1.
