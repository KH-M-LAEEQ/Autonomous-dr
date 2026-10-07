"""SimulatedProvider -- Week 3's `CloudProvider` implementation.

8 resources across 3 fake regions and 2 fake tenants (matching the demo
tenants seeded in migration 0001). Metrics follow a daily seasonality curve
plus Gaussian noise; `inject_fault` (backed by `core.faults`, so it is visible
to the collector running in a different process) overrides specific signals
for a bounded duration -- that override IS the fault, not a separate failure
model, so a 24-hour collector run naturally produces labelled anomalies
whenever the demo fault button is used.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime

from core import faults
from core.interfaces.cloud_provider import CloudProvider
from core.models.domain import Action, CostEstimate, HealthReport, Resource
from core.models.enums import ActionType, HealthState, ProviderName
from core.signals import CANONICAL_SIGNALS

REGIONS: tuple[str, ...] = ("sim-us-east-1", "sim-eu-west-1", "sim-ap-south-1")
TENANTS: tuple[str, ...] = ("tenant-a", "tenant-b")

FAULT_TYPES: tuple[str, ...] = ("cpu_hog", "latency", "stop", "pause", "region_down")

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
# (byte/count rates); percentages cap at 100.
Baseline = tuple[float, float, float]

_DEFAULT_BASELINE: dict[str, Baseline] = {
    "cpu_pct": (30.0, 8.0, 100.0),
    "memory_pct": (40.0, 8.0, 100.0),
    "disk_used_pct": (55.0, 3.0, 100.0),
    "disk_read_bytes_per_s": (2_000_000.0, 500_000.0, math.inf),
    "disk_write_bytes_per_s": (1_000_000.0, 300_000.0, math.inf),
    "network_in_bytes_per_s": (5_000_000.0, 1_000_000.0, math.inf),
    "network_out_bytes_per_s": (6_000_000.0, 1_200_000.0, math.inf),
    "request_rate_per_s": (50.0, 10.0, math.inf),
    "error_rate_pct": (0.5, 0.3, 100.0),
    "latency_p50_ms": (40.0, 8.0, math.inf),
    "latency_p95_ms": (120.0, 20.0, math.inf),
    "latency_p99_ms": (220.0, 40.0, math.inf),
    "active_connections": (80.0, 15.0, math.inf),
    "queue_depth": (5.0, 3.0, math.inf),
    "http_5xx_rate_pct": (0.2, 0.15, 100.0),
    "http_4xx_rate_pct": (1.0, 0.5, 100.0),
    "db_connections_used": (0.0, 0.0, math.inf),
    "db_query_latency_p95_ms": (0.0, 0.0, math.inf),
    "cache_hit_rate_pct": (0.0, 0.0, 100.0),
    "uptime_pct": (99.95, 0.05, 100.0),
}

# Overrides layered on top of the default baseline, per resource kind.
_KIND_BASELINES: dict[str, dict[str, Baseline]] = {
    "database": {
        "cpu_pct": (45.0, 10.0, 100.0),
        "request_rate_per_s": (20.0, 5.0, math.inf),
        "db_connections_used": (40.0, 10.0, math.inf),
        "db_query_latency_p95_ms": (25.0, 8.0, math.inf),
    },
    "cache": {
        "memory_pct": (60.0, 8.0, 100.0),
        "latency_p50_ms": (2.0, 1.0, math.inf),
        "cache_hit_rate_pct": (92.0, 4.0, 100.0),
    },
    "worker": {
        "cpu_pct": (50.0, 12.0, 100.0),
        "request_rate_per_s": (5.0, 2.0, math.inf),
        "queue_depth": (15.0, 6.0, math.inf),
    },
    "load_balancer": {
        "request_rate_per_s": (200.0, 30.0, math.inf),
        "active_connections": (300.0, 50.0, math.inf),
        "network_in_bytes_per_s": (15_000_000.0, 2_000_000.0, math.inf),
        "network_out_bytes_per_s": (18_000_000.0, 2_500_000.0, math.inf),
    },
}

# Signals that track daily load rather than staying roughly constant.
_SEASONAL_SIGNALS: frozenset[str] = frozenset(
    {
        "cpu_pct",
        "memory_pct",
        "network_in_bytes_per_s",
        "network_out_bytes_per_s",
        "request_rate_per_s",
        "active_connections",
        "queue_depth",
        "disk_read_bytes_per_s",
        "disk_write_bytes_per_s",
        "db_connections_used",
    }
)


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


def get_resource(resource_id: str) -> Resource | None:
    """Public lookup for callers outside this module (e.g.
    `core.providers.simulated_executor`) that need to validate a resource id
    without reaching into the private `_RESOURCE_BY_ID` table directly."""
    return _RESOURCE_BY_ID.get(resource_id)


def applicable_signals(kind: str) -> tuple[str, ...]:
    """Signals this resource kind reports. Everything else is null for it."""
    na = _NOT_APPLICABLE_BY_KIND.get(kind, frozenset())
    return tuple(s for s in ALL_COLLECTED_SIGNALS if s not in na)


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
    for signal in CANONICAL_SIGNALS:
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


def _apply_fault(
    signals: dict[str, float], fault_type: str
) -> tuple[dict[str, float], HealthState, str]:
    """Faults override specific signals in-place; they do not replace the
    seasonal/noise model, so the pre-fault baseline is still visible in the
    signals a fault doesn't touch."""
    if fault_type == "cpu_hog":
        signals["cpu_pct"] = _clamp(random.gauss(97.0, 2.0), 100.0)
        signals["latency_p95_ms"] *= 3.0
        signals["latency_p99_ms"] *= 4.0
        return signals, HealthState.DEGRADED, "cpu_hog fault active"

    if fault_type == "latency":
        signals["latency_p50_ms"] *= 6.0
        signals["latency_p95_ms"] *= 8.0
        signals["latency_p99_ms"] *= 10.0
        signals["error_rate_pct"] = _clamp(signals["error_rate_pct"] + 5.0, 100.0)
        return signals, HealthState.DEGRADED, "latency fault active"

    if fault_type in ("stop", "pause", "region_down"):
        for signal in signals:
            signals[signal] = 0.0
        signals["error_rate_pct"] = 100.0
        signals["http_5xx_rate_pct"] = 100.0
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

        signals = _generate_signals(resource, now)
        fault_type = faults.get_fault(resource.id) or self._region_fault(resource.region)
        state = HealthState.HEALTHY
        message = None
        if fault_type is not None:
            signals, state, message = _apply_fault(signals, fault_type)

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

    def inject_fault(self, resource_id: str, fault_type: str, duration_seconds: int) -> None:
        """Convenience method for the demo fault button -- not part of the
        frozen `CloudProvider` contract, just this concrete class's own API."""
        if resource_id not in _RESOURCE_BY_ID:
            raise KeyError(f"unknown resource {resource_id!r}")
        if fault_type not in FAULT_TYPES:
            raise ValueError(f"unknown fault type {fault_type!r}; expected one of {FAULT_TYPES}")
        faults.set_fault(resource_id, fault_type, duration_seconds)

    def _region_fault(self, region: str) -> str | None:
        """A `region_down` fault injected against any one resource takes the
        whole region down -- the API only asks for a resource_id, so this is
        how a single resource-scoped fault propagates to its region."""
        for resource in _RESOURCES:
            if resource.region == region and faults.get_fault(resource.id) == "region_down":
                return "region_down"
        return None
