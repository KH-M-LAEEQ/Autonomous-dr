"""SimulatedProvider -- Week 3's `CloudProvider` implementation.

8 resources across 3 fake regions and 2 fake tenants (matching the demo
tenants seeded in migration 0001). Metrics follow a daily seasonality curve
plus Gaussian noise; `inject_fault` (backed by `core.faults`, so it is visible
to the collector running in a different process) overrides specific signals
for a bounded duration -- that override IS the fault, not a separate failure
model, so a 24-hour collector run naturally produces labelled anomalies
whenever the demo fault button is used.

Signal names and units come from `core/signals.py` / `docs/metric-schema.md`.
Two consequences worth stating because they are easy to get wrong:

**A signal that does not apply to a resource kind is omitted, never zeroed.**
A worker has no `request_rate`; a cache has no `replication_lag_seconds`. The
key is absent from `HealthReport.signals`, which is how null travels (see
`core/signals.py`). Returning 0.0 would be a measurement claiming the value
really is zero, and a detector would learn that as normal.

**`uptime_seconds` is monotonic between restarts.** It is derived from a
per-resource boot time, not drawn from a baseline distribution, so it climbs
with the clock and *drops to zero* when a restart-class fault (`stop`, `pause`,
`region_down`) hits. The drop is the signal; the ramp carries no information,
which is why `core/signals.py` keeps it out of detector features.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime

from core import faults
from core.interfaces.cloud_provider import CloudProvider
from core.models.domain import Action, CostEstimate, HealthReport, Resource
from core.models.enums import ActionType, HealthState, ProviderName
from core.signals import ALL_COLLECTED_SIGNALS

REGIONS: tuple[str, ...] = ("sim-us-east-1", "sim-eu-west-1", "sim-ap-south-1")
TENANTS: tuple[str, ...] = ("tenant-a", "tenant-b")

FAULT_TYPES: tuple[str, ...] = (
    "cpu_hog",
    "latency",
    "stop",
    "pause",
    "region_down",
    # Added for the Week 10 harness: the three above that pin signals to an
    # extreme are trivially detectable, which tells you nothing about a
    # detector. These two are deliberately subtle.
    "cpu_ramp",  # severity scales with `intensity`, for a gradual climb
    "cpu_step_small",  # a small fixed bump, well inside normal noise envelopes
)

#: Faults that mean the resource restarted, so `uptime_seconds` resets.
_RESTART_FAULTS: frozenset[str] = frozenset({"stop", "pause", "region_down"})

_RESOURCES: tuple[Resource, ...] = (
    Resource(
        id="sim-web-1",
        provider=ProviderName.SIMULATED,
        region="sim-us-east-1",
        tenant_id="tenant-a",
        kind="web_service",
        name="checkout-web",
    ),
    Resource(
        id="sim-web-2",
        provider=ProviderName.SIMULATED,
        region="sim-eu-west-1",
        tenant_id="tenant-a",
        kind="web_service",
        name="catalog-web",
    ),
    Resource(
        id="sim-db-1",
        provider=ProviderName.SIMULATED,
        region="sim-us-east-1",
        tenant_id="tenant-a",
        kind="database",
        name="orders-db",
    ),
    Resource(
        id="sim-cache-1",
        provider=ProviderName.SIMULATED,
        region="sim-ap-south-1",
        tenant_id="tenant-a",
        kind="cache",
        name="session-cache",
    ),
    Resource(
        id="sim-web-3",
        provider=ProviderName.SIMULATED,
        region="sim-us-east-1",
        tenant_id="tenant-b",
        kind="web_service",
        name="storefront-web",
    ),
    Resource(
        id="sim-db-2",
        provider=ProviderName.SIMULATED,
        region="sim-eu-west-1",
        tenant_id="tenant-b",
        kind="database",
        name="inventory-db",
    ),
    Resource(
        id="sim-worker-1",
        provider=ProviderName.SIMULATED,
        region="sim-ap-south-1",
        tenant_id="tenant-b",
        kind="worker",
        name="billing-worker",
    ),
    Resource(
        id="sim-lb-1",
        provider=ProviderName.SIMULATED,
        region="sim-us-east-1",
        tenant_id="tenant-b",
        kind="load_balancer",
        name="edge-lb",
    ),
)

_RESOURCE_BY_ID: dict[str, Resource] = {r.id: r for r in _RESOURCES}

#: Bumped whenever a change here affects what a generated dataset looks like
#: (ADR convention: a dataset's manifest records which version produced it).
#: v1-v5 predate this constant and are not touched or relabelled -- only
#: datasets generated from here on carry it. 2: the clamp-at-zero fix below.
#: 3: latency switched from a normal draw to a log-normal one (same mean/std,
#: different shape -- see `_draw_latency`), so a regenerated dataset's
#: latency columns would carry a different low-tail shape than v1-v5's.
SIMULATOR_VERSION = 3

# (mean, std, ceiling) per signal. `math.inf` ceiling means "no natural cap"
# (byte/count rates); percentages cap at 100 and fractions at 1.
Baseline = tuple[float, float, float]

_DEFAULT_BASELINE: dict[str, Baseline] = {
    # Compute
    "cpu_percent": (30.0, 8.0, 100.0),
    "memory_percent": (40.0, 8.0, 100.0),
    "disk_used_percent": (55.0, 3.0, 100.0),
    "disk_io_ops": (300.0, 80.0, math.inf),
    "process_count": (120.0, 12.0, math.inf),
    # Network
    "net_in_bytes": (5_000_000.0, 1_000_000.0, math.inf),
    "net_out_bytes": (6_000_000.0, 1_200_000.0, math.inf),
    "net_packets_dropped": (0.5, 0.3, math.inf),
    "active_connections": (80.0, 15.0, math.inf),
    # Service health -- error rates are FRACTIONS (0-1), not percentages
    "request_rate": (50.0, 10.0, math.inf),
    "error_rate_5xx": (0.002, 0.0015, 1.0),
    "error_rate_4xx": (0.010, 0.005, 1.0),
    "latency_p50": (40.0, 8.0, math.inf),
    "latency_p95": (120.0, 20.0, math.inf),
    "latency_p99": (220.0, 40.0, math.inf),
    # Availability -- uptime_seconds is derived, not drawn (see module docstring)
    "health_check_pass": (1.0, 0.0, 1.0),
    "healthy_target_count": (4.0, 0.0, math.inf),
    "uptime_seconds": (0.0, 0.0, math.inf),
    # Saturation
    "queue_depth": (5.0, 3.0, math.inf),
    "throttle_count": (0.1, 0.1, math.inf),
    # Reserve
    "replication_lag_seconds": (0.4, 0.2, math.inf),
    "tcp_retransmit_rate": (0.001, 0.0008, 1.0),
    "swap_used_percent": (2.0, 1.0, 100.0),
    "open_file_descriptors": (1200.0, 150.0, math.inf),
    "gc_pause_ms": (0.0, 0.0, math.inf),
}

# Overrides layered on top of the default baseline, per resource kind.
_KIND_BASELINES: dict[str, dict[str, Baseline]] = {
    "database": {
        "cpu_percent": (45.0, 10.0, 100.0),
        "request_rate": (20.0, 5.0, math.inf),
        "active_connections": (40.0, 10.0, math.inf),
        "latency_p95": (25.0, 8.0, math.inf),
        "latency_p99": (60.0, 15.0, math.inf),
        "throttle_count": (0.2, 0.15, math.inf),
        "disk_io_ops": (900.0, 200.0, math.inf),
    },
    "cache": {
        "memory_percent": (60.0, 8.0, 100.0),
        "latency_p50": (2.0, 1.0, math.inf),
        "latency_p95": (5.0, 2.0, math.inf),
        "latency_p99": (9.0, 3.0, math.inf),
    },
    "worker": {
        "cpu_percent": (50.0, 12.0, 100.0),
        "process_count": (60.0, 8.0, math.inf),
        "queue_depth": (15.0, 6.0, math.inf),
    },
    "load_balancer": {
        "request_rate": (200.0, 30.0, math.inf),
        "active_connections": (300.0, 50.0, math.inf),
        "net_in_bytes": (15_000_000.0, 2_000_000.0, math.inf),
        "net_out_bytes": (18_000_000.0, 2_500_000.0, math.inf),
    },
}

# Request-path metrics. `docs/metric-schema.md` notes that signals 9 and 10-15
# are load-balancer / ALB metrics which "a bare instance has none of on any
# provider" -- a queue-driven worker is the case where that bites.
_REQUEST_PATH: frozenset[str] = frozenset(
    {
        "active_connections",
        "request_rate",
        "error_rate_5xx",
        "error_rate_4xx",
        "latency_p50",
        "latency_p95",
        "latency_p99",
    }
)

# Signals that do NOT apply per kind, and are therefore omitted (= null).
# `gc_pause_ms` is absent everywhere: the schema calls it testbed-only.
_NOT_APPLICABLE_BY_KIND: dict[str, frozenset[str]] = {
    "web_service": frozenset(
        {"healthy_target_count", "queue_depth", "throttle_count", "replication_lag_seconds"}
    )
    | {"gc_pause_ms"},
    "database": frozenset({"healthy_target_count", "queue_depth", "gc_pause_ms"}),
    "cache": frozenset(
        {"healthy_target_count", "queue_depth", "throttle_count", "replication_lag_seconds"}
    )
    | {"gc_pause_ms"},
    "worker": _REQUEST_PATH
    | frozenset({"healthy_target_count", "replication_lag_seconds", "gc_pause_ms"}),
    "load_balancer": frozenset(
        {"queue_depth", "throttle_count", "replication_lag_seconds", "gc_pause_ms"}
    ),
}

# Signals that track daily load rather than staying roughly constant.
_SEASONAL_SIGNALS: frozenset[str] = frozenset(
    {
        "cpu_percent",
        "memory_percent",
        "net_in_bytes",
        "net_out_bytes",
        "request_rate",
        "active_connections",
        "queue_depth",
        "disk_io_ops",
        "throttle_count",
    }
)

#: Per-resource boot time, so `uptime_seconds` is monotonic between restarts.
_BOOT_TIME: dict[str, datetime] = {}


def get_resource(resource_id: str) -> Resource | None:
    """Public lookup for callers outside this module (e.g.
    `core.providers.simulated_executor`) that need to validate a resource id
    without reaching into the private `_RESOURCE_BY_ID` table directly."""
    return _RESOURCE_BY_ID.get(resource_id)


def applicable_signals(kind: str) -> tuple[str, ...]:
    """Signals this resource kind reports. Everything else is null for it."""
    na = _NOT_APPLICABLE_BY_KIND.get(kind, frozenset())
    return tuple(s for s in ALL_COLLECTED_SIGNALS if s not in na)


#: Signals audited for the clamp-at-zero pattern (every entry in
#: `_DEFAULT_BASELINE` was checked): these three are the only ones where
#: 0.0 is never a real reading, just where the floor used to land. A
#: completed operation cannot take zero time -- unlike, say,
#: `error_rate_5xx` or `throttle_count` (genuinely 0 whenever nothing went
#: wrong) or `replication_lag_seconds` (genuinely 0 when fully caught up).
#: Counts like `process_count`/`open_file_descriptors` have the same
#: theoretical floor-at-zero shape but sit 8-10 standard deviations from
#: it, so they never actually clamp -- left alone rather than changed with
#: no observable effect. Floored at 0.1 (the signal's own unit -- ms, per
#: docs/metric-schema.md) instead of 0.0; the mean is unchanged, only the
#: rare low tail moves.
#:
#: Now a safety net rather than the normal case: `_draw_latency` draws from
#: a log-normal, which is strictly positive by construction, so a real
#: draw landing at or below 0.1 should be astronomically rare (measured:
#: 0/5000 for sim-cache-1's latency_p50, the baseline closest to zero --
#: see `test_sim_cache_1_latency_p50_never_piles_up_on_the_floor`). Kept in
#: case a future baseline is edited to sit much closer to zero, or a fault
#: multiplier pushes a draw down rather than up.
_POSITIVE_FLOOR: dict[str, float] = {
    "latency_p50": 0.1,
    "latency_p95": 0.1,
    "latency_p99": 0.1,
}

#: The three signals `_draw_latency` covers. Always present together or
#: absent together (every kind's `_NOT_APPLICABLE_BY_KIND` entry excludes
#: all of `_REQUEST_PATH`, never a subset of it), which is what lets
#: `_enforce_latency_ordering` assume a complete triplet when any one of
#: them is present.
_LATENCY_SIGNALS: frozenset[str] = frozenset({"latency_p50", "latency_p95", "latency_p99"})


def _clamp(value: float, ceiling: float, floor: float = 0.0) -> float:
    return max(floor, min(value, ceiling))


def _lognormal_params(mean: float, std: float) -> tuple[float, float]:
    """`(mu, sigma)` for `random.lognormvariate` such that the draw's own
    mean and std -- on the real, non-log scale -- equal `mean`/`std`
    exactly. Standard moment-matching identities for a log-normal:
    `sigma**2 = ln(1 + (std/mean)**2)`, `mu = ln(mean) - sigma**2/2`.
    Every latency baseline has `mean > 0`, so this never divides by zero or
    logs a non-positive number.
    """
    sigma_squared = math.log(1.0 + (std / mean) ** 2)
    mu = math.log(mean) - sigma_squared / 2.0
    return mu, math.sqrt(sigma_squared)


def _draw_latency(mean: float, std: float) -> float:
    """Log-normal instead of Gaussian: same mean and std as the baseline
    (via `_lognormal_params`), but a right-skewed shape that is strictly
    positive and has a much lighter left tail -- a completed request's
    latency looks like this in practice, and it is also why the
    clamp-at-zero floor stops being load-bearing (see `_POSITIVE_FLOOR`).
    `std <= 0` only happens if a future baseline sets it to exactly 0,
    which `random.gauss` elsewhere in this module already treats as
    "always return the mean"; mirrored here for the same reason."""
    if std <= 0:
        return mean
    mu, sigma = _lognormal_params(mean, std)
    return random.lognormvariate(mu, sigma)


def _enforce_latency_ordering(signals: dict[str, float]) -> None:
    """`latency_p50 <= latency_p95 <= latency_p99` must hold in every
    reading, but `_draw_latency` draws each one independently, which can
    invert the order in the tails (most likely for sim-cache-1, whose three
    baselines sit closest together). Chaining a forward max -- rather than
    re-drawing on inversion -- only nudges the rare inverted case up to
    match its neighbour; it never touches the common case where the order
    already holds, so it does not bias the bulk of the distribution."""
    if "latency_p95" in signals and "latency_p50" in signals:
        signals["latency_p95"] = max(signals["latency_p95"], signals["latency_p50"])
    if "latency_p99" in signals and "latency_p95" in signals:
        signals["latency_p99"] = max(signals["latency_p99"], signals["latency_p95"])


def _seasonal_factor(now: datetime) -> float:
    """0..1, peaking at midday and troughing at midnight -- business-hours traffic."""
    hour = now.hour + now.minute / 60
    return 0.5 + 0.5 * math.sin(2 * math.pi * (hour - 6) / 24)


def _baseline_for(kind: str) -> dict[str, Baseline]:
    return {**_DEFAULT_BASELINE, **_KIND_BASELINES.get(kind, {})}


def _uptime_seconds(resource_id: str, now: datetime) -> float:
    boot = _BOOT_TIME.setdefault(resource_id, now)
    return max(0.0, (now - boot).total_seconds())


def _generate_signals(resource: Resource, now: datetime) -> dict[str, float]:
    """One reading per applicable signal. Non-applicable signals are absent.

    Latency is drawn, ordering-enforced, and floor-clamped only after every
    other signal is in hand: `_enforce_latency_ordering` needs the raw p50/
    p95/p99 draws together, and the floor is meant to catch what ordering
    enforcement cannot (see `_POSITIVE_FLOOR`), so it runs last.
    """
    baseline = _baseline_for(resource.kind)
    factor = _seasonal_factor(now)
    signals: dict[str, float] = {}
    for signal in applicable_signals(resource.kind):
        if signal == "uptime_seconds":
            signals[signal] = _uptime_seconds(resource.id, now)
            continue
        mean, std, ceiling = baseline[signal]
        scaled_mean = mean * factor if signal in _SEASONAL_SIGNALS else mean
        if signal in _LATENCY_SIGNALS:
            signals[signal] = _draw_latency(scaled_mean, std)
        else:
            value = random.gauss(scaled_mean, std) if std > 0 else scaled_mean
            signals[signal] = _clamp(value, ceiling, _POSITIVE_FLOOR.get(signal, 0.0))

    _enforce_latency_ordering(signals)
    for signal in _LATENCY_SIGNALS:
        if signal in signals:
            _, _, ceiling = baseline[signal]
            signals[signal] = _clamp(signals[signal], ceiling, _POSITIVE_FLOOR.get(signal, 0.0))
    return signals


def _scale_present(signals: dict[str, float], signal: str, factor: float) -> None:
    """Multiply a signal only if the resource actually reports it."""
    if signal in signals:
        signals[signal] *= factor


def _set_present(signals: dict[str, float], signal: str, value: float) -> None:
    if signal in signals:
        signals[signal] = value


def _apply_fault(
    signals: dict[str, float], fault_type: str, intensity: float = 1.0
) -> tuple[dict[str, float], HealthState, str]:
    """Faults override specific signals in-place; they do not replace the
    seasonal/noise model, so the pre-fault baseline is still visible in the
    signals a fault doesn't touch. Absent signals are never introduced -- a
    fault cannot give a worker a `request_rate` it does not have."""
    if fault_type == "cpu_hog":
        _set_present(signals, "cpu_percent", _clamp(random.gauss(97.0, 2.0), 100.0))
        _scale_present(signals, "latency_p95", 3.0)
        _scale_present(signals, "latency_p99", 4.0)
        return signals, HealthState.DEGRADED, "cpu_hog fault active"

    if fault_type == "cpu_ramp":
        # Climbs from the current baseline to cpu_hog severity as intensity
        # goes 0 -> 1. Early ticks are inside normal noise on purpose.
        current = signals.get("cpu_percent", 0.0)
        target = _clamp(random.gauss(97.0, 2.0), 100.0)
        level = _clamp(intensity, 1.0)
        _set_present(signals, "cpu_percent", current + (target - current) * level)
        _scale_present(signals, "latency_p95", 1.0 + 2.0 * level)
        _scale_present(signals, "latency_p99", 1.0 + 3.0 * level)
        state = HealthState.DEGRADED if level > 0.5 else HealthState.HEALTHY
        return signals, state, f"cpu_ramp fault active at intensity {level:.2f}"

    if fault_type == "cpu_step_small":
        # +15 points. Baseline cpu std is 8-12, so this is under two sigma:
        # detectable only by something that models the signal, not by eye.
        _set_present(signals, "cpu_percent", _clamp(signals.get("cpu_percent", 0.0) + 15.0, 100.0))
        return signals, HealthState.DEGRADED, "cpu_step_small fault active"

    if fault_type == "latency":
        _scale_present(signals, "latency_p50", 6.0)
        _scale_present(signals, "latency_p95", 8.0)
        _scale_present(signals, "latency_p99", 10.0)
        if "error_rate_5xx" in signals:
            signals["error_rate_5xx"] = _clamp(signals["error_rate_5xx"] + 0.05, 1.0)
        return signals, HealthState.DEGRADED, "latency fault active"

    if fault_type in _RESTART_FAULTS:
        for signal in signals:
            signals[signal] = 0.0
        # Error rates are fractions: a total outage is 1.0, not 100.
        _set_present(signals, "error_rate_5xx", 1.0)
        _set_present(signals, "health_check_pass", 0.0)
        return signals, HealthState.UNHEALTHY, f"{fault_type} fault active"

    return signals, HealthState.HEALTHY, "unknown fault type ignored"


# Static per-action-type price table. The real cost estimator (budget gate,
# live pricing APIs) is Week 5 / Week 12; this exists only so `CloudProvider`
# always returns a usable `CostEstimate`, never `None`, per the interface
# contract.
_STATIC_PRICE_USD: dict[ActionType, float] = {
    ActionType.DNS_WEIGHT_SHIFT: 0.01,
    ActionType.TRAFFIC_REROUTE: 0.01,
    ActionType.SCALE_OUT: 0.50,
    ActionType.REGION_FAILOVER: 5.00,
    ActionType.CROSS_CLOUD_FAILOVER: 8.00,
    ActionType.DR_PROMOTION: 20.00,
    ActionType.NO_OP: 0.00,
}


def _parse_fault(raw: str) -> tuple[str, float]:
    """Fault values are `name` or `name:intensity` -- the intensity suffix is
    what lets a ramp advance while still going through the one-string Redis
    fault API in `core.faults`."""
    name, _, suffix = raw.partition(":")
    if not suffix:
        return name, 1.0
    try:
        return name, float(suffix)
    except ValueError:
        return name, 1.0


class SimulatedProvider(CloudProvider):
    """8 resources, 3 regions, 2 tenants, in-process -- no network calls."""

    name = ProviderName.SIMULATED

    async def get_health(self, resource_id: str) -> HealthReport:
        resource = _RESOURCE_BY_ID.get(resource_id)
        now = datetime.now(UTC)
        if resource is None:
            return HealthReport(
                resource_id=resource_id,
                state=HealthState.UNKNOWN,
                observed_at=now,
                signals={},
                message="unknown resource",
            )

        raw = faults.get_fault(resource.id) or self._region_fault(resource.region)
        fault_type, intensity = _parse_fault(raw) if raw else (None, 1.0)

        # Reset the boot clock BEFORE generating, so uptime reads 0 during the
        # outage and climbs from 0 once the fault clears.
        if fault_type in _RESTART_FAULTS:
            _BOOT_TIME[resource.id] = now

        signals = _generate_signals(resource, now)
        state = HealthState.HEALTHY
        message = None
        if fault_type is not None:
            signals, state, message = _apply_fault(signals, fault_type, intensity)

        return HealthReport(
            resource_id=resource.id, state=state, observed_at=now, signals=signals, message=message
        )

    async def list_resources(self, tenant_id: str) -> list[Resource]:
        return [r for r in _RESOURCES if r.tenant_id == tenant_id]

    async def estimate_cost(self, action: Action) -> CostEstimate:
        price = _STATIC_PRICE_USD.get(action.type, 0.0)
        return CostEstimate(
            action_id=action.id,
            one_off_usd=price,
            hourly_usd=0.0,
            projected_monthly_usd=price * 4,
            confidence=0.4,
            source="static_table",
            breakdown={"base": price},
        )

    async def execute(self, action: Action) -> str:
        return f"sim-exec-{action.id}"

    async def get_regions(self) -> list[str]:
        return list(REGIONS)

    def inject_fault(
        self,
        resource_id: str,
        fault_type: str,
        duration_seconds: int,
        intensity: float | None = None,
    ) -> None:
        """Convenience method for the demo fault button and the dataset
        generator -- not part of the frozen `CloudProvider` contract, just this
        concrete class's own API.

        `intensity` only means anything to `cpu_ramp`; re-injecting with a
        rising intensity is how a gradual fault advances.
        """
        if resource_id not in _RESOURCE_BY_ID:
            raise KeyError(f"unknown resource {resource_id!r}")
        if fault_type not in FAULT_TYPES:
            raise ValueError(f"unknown fault type {fault_type!r}; expected one of {FAULT_TYPES}")
        value = fault_type if intensity is None else f"{fault_type}:{intensity}"
        faults.set_fault(resource_id, value, duration_seconds)

    def _region_fault(self, region: str) -> str | None:
        """A `region_down` fault injected against any one resource takes the
        whole region down -- the API only asks for a resource_id, so this is
        how a single resource-scoped fault propagates to its region."""
        for resource in _RESOURCES:
            if resource.region == region and faults.get_fault(resource.id) == "region_down":
                return "region_down"
        return None
