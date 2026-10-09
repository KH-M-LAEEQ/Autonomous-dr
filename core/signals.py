"""The canonical telemetry signal list -- `docs/metric-schema.md` is the spec.

The collector writes **25** fields: the 20 canonical signals plus the 5 reserve
ones. Reserve signals are collected and nothing reads them yet; promoting one to
canonical is an ADR, not a migration, and it is only cheap because the history
is already there (see `docs/metric-schema.md`).

Every `CloudProvider.get_health().signals` dict and every `MetricWindow.values`
dict uses these exact names and units, whether the reading came from the
simulator, AWS CloudWatch, or Azure Monitor. Week 9's normalisation layer maps
provider-native metric names onto this list; it never grows a provider-specific
key instead.

**Absent is null, and null is not zero.** A signal that does not apply to a
resource (`healthy_target_count` on a worker, `replication_lag_seconds` on a
cache) is *omitted from the dict*, never written as 0.0. Omission is how null is
represented end to end: InfluxDB has no null, so a field that is not written
reads back as null, and a `0.0` would instead be a real measurement claiming the
thing is at zero. Consumers must treat a missing key as "no reading" --
`ml/detectors/*` skip them rather than imputing.

Changing this list after the collector has been running invalidates every
episode already recorded against the old shape. Datasets record the list's
hash for exactly that reason (`ml/datasets/make_episodes.py`).
"""

from typing import Final

# -- the 20 canonical signals, grouped as docs/metric-schema.md groups them ----

#: Compute (5)
_COMPUTE: Final[tuple[str, ...]] = (
    "cpu_percent",  # 0-100
    "memory_percent",  # 0-100
    "disk_used_percent",  # 0-100
    "disk_io_ops",  # ops/s
    "process_count",  # count
)

#: Network (4)
_NETWORK: Final[tuple[str, ...]] = (
    "net_in_bytes",  # bytes/s
    "net_out_bytes",  # bytes/s
    "net_packets_dropped",  # count/s
    "active_connections",  # count
)

#: Service health (6)
_SERVICE_HEALTH: Final[tuple[str, ...]] = (
    "request_rate",  # req/s
    "error_rate_5xx",  # 0-1 FRACTION, not a percentage
    "error_rate_4xx",  # 0-1 FRACTION, not a percentage
    "latency_p50",  # ms
    "latency_p95",  # ms
    "latency_p99",  # ms
)

#: Availability (3)
_AVAILABILITY: Final[tuple[str, ...]] = (
    "health_check_pass",  # 0 or 1
    "healthy_target_count",  # count
    "uptime_seconds",  # seconds, monotonically increasing between restarts
)

#: Saturation (2)
_SATURATION: Final[tuple[str, ...]] = (
    "queue_depth",  # count
    "throttle_count",  # count/s
)

CANONICAL_SIGNALS: Final[tuple[str, ...]] = (
    *_COMPUTE,
    *_NETWORK,
    *_SERVICE_HEALTH,
    *_AVAILABILITY,
    *_SATURATION,
)

#: Collected alongside the canonical 20; nothing consumes them yet.
#: `replication_lag_seconds` is the most likely promotion -- see the schema doc.
RESERVE_SIGNALS: Final[tuple[str, ...]] = (
    "replication_lag_seconds",  # seconds
    "tcp_retransmit_rate",  # 0-1
    "swap_used_percent",  # 0-100
    "open_file_descriptors",  # count
    "gc_pause_ms",  # ms
)

#: Everything the collector writes.
ALL_COLLECTED_SIGNALS: Final[tuple[str, ...]] = (*CANONICAL_SIGNALS, *RESERVE_SIGNALS)

#: `uptime_seconds` is canonical and collected, but it is a monotonically
#: increasing counter: as a raw feature its value only encodes "how long since
#: the last restart", so a detector fitted on it learns a ramp and flags the
#: passage of time. What matters is the *drop* when a resource restarts, which
#: is a different computation than the one every detector here applies. Until a
#: detector derives that delta explicitly, it stays out of the feature set.
NON_FEATURE_SIGNALS: Final[frozenset[str]] = frozenset({"uptime_seconds"})

#: What `ml/detectors/*` actually score. Canonical only -- reserve signals are
#: not consumed by anything (docs/metric-schema.md) -- minus the non-features.
DETECTOR_SIGNALS: Final[tuple[str, ...]] = tuple(
    s for s in CANONICAL_SIGNALS if s not in NON_FEATURE_SIGNALS
)

#: Signals carrying a 0-1 fraction rather than a 0-100 percentage. The two
#: metric drafts disagreed on this by a factor of 100, so it is asserted below
#: and named here rather than left to each call site to remember.
FRACTION_SIGNALS: Final[frozenset[str]] = frozenset(
    {"error_rate_5xx", "error_rate_4xx", "tcp_retransmit_rate"}
)

#: Signals carrying a 0-100 percentage.
PERCENT_SIGNALS: Final[frozenset[str]] = frozenset(
    {"cpu_percent", "memory_percent", "disk_used_percent", "swap_used_percent"}
)

assert len(CANONICAL_SIGNALS) == 20, "the metric schema is exactly 20 canonical signals"
assert len(RESERVE_SIGNALS) == 5, "the metric schema is exactly 5 reserve signals"
assert len(ALL_COLLECTED_SIGNALS) == 25, "the collector writes exactly 25 fields"
assert len(set(ALL_COLLECTED_SIGNALS)) == 25, "signal names must be unique"
assert len(DETECTOR_SIGNALS) == 19, "detector inputs are the canonical 20 minus uptime_seconds"
assert set(ALL_COLLECTED_SIGNALS) >= FRACTION_SIGNALS
assert set(ALL_COLLECTED_SIGNALS) >= PERCENT_SIGNALS
assert not (FRACTION_SIGNALS & PERCENT_SIGNALS), "a signal is either a fraction or a percentage"
