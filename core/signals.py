"""The 20 canonical telemetry signals (Week 3, AI role decision).

Every `CloudProvider.get_health().signals` dict and every `MetricWindow.values`
dict uses these exact keys, whether the reading came from the simulator, AWS
CloudWatch, or Azure Monitor (Week 9's normalisation layer maps provider-native
metric names onto this list — it never grows a provider-specific key instead).

Changing this list after the collector has been running invalidates every
episode already recorded (ml/datasets/) against the old shape. See
docs/metrics.md for the rationale behind the selection.
"""

from typing import Final

CANONICAL_SIGNALS: Final[tuple[str, ...]] = (
    "cpu_pct",
    "memory_pct",
    "disk_used_pct",
    "disk_read_bytes_per_s",
    "disk_write_bytes_per_s",
    "network_in_bytes_per_s",
    "network_out_bytes_per_s",
    "request_rate_per_s",
    "error_rate_pct",
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "active_connections",
    "queue_depth",
    "http_5xx_rate_pct",
    "http_4xx_rate_pct",
    "db_connections_used",
    "db_query_latency_p95_ms",
    "cache_hit_rate_pct",
    "uptime_pct",
)

assert len(CANONICAL_SIGNALS) == 20, "the metric schema decision is for exactly 20 signals"
