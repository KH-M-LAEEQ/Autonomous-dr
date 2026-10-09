"""Tests for core/providers/simulated.py.

Fault state is backed by Redis in production (core/faults.py), so these
monkeypatch `core.faults` with an in-memory dict -- the provider's own logic
is what's under test here, not Redis.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from core import faults
from core.models.enums import HealthState, ProviderName
from core.providers import simulated as simulated_module
from core.providers.simulated import (
    REGIONS,
    TENANTS,
    SimulatedProvider,
    applicable_signals,
)
from core.signals import (
    ALL_COLLECTED_SIGNALS,
    CANONICAL_SIGNALS,
    DETECTOR_SIGNALS,
    FRACTION_SIGNALS,
    PERCENT_SIGNALS,
)


@pytest.fixture(autouse=True)
def fake_fault_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    store: dict[str, str] = {}
    monkeypatch.setattr(faults, "set_fault", lambda rid, ft, dur: store.__setitem__(rid, ft))
    monkeypatch.setattr(faults, "get_fault", lambda rid: store.get(rid))
    monkeypatch.setattr(faults, "clear_fault", lambda rid: store.pop(rid, None))
    return store


@pytest.fixture(autouse=True)
def _reset_boot_times() -> None:
    """`_BOOT_TIME` is module state backing `uptime_seconds`; a leak between
    tests would make uptime assertions order-dependent."""
    simulated_module._BOOT_TIME.clear()


@pytest.fixture
def provider() -> SimulatedProvider:
    return SimulatedProvider()


async def test_eight_resources_three_regions_two_tenants(provider: SimulatedProvider) -> None:
    all_resources = [r for tenant in TENANTS for r in await provider.list_resources(tenant)]
    assert len(all_resources) == 8
    assert {r.region for r in all_resources} == set(REGIONS)
    assert {r.tenant_id for r in all_resources} == set(TENANTS)
    assert len(REGIONS) == 3
    assert len(TENANTS) == 2


async def test_list_resources_filters_by_tenant(provider: SimulatedProvider) -> None:
    tenant_a = await provider.list_resources("tenant-a")
    tenant_b = await provider.list_resources("tenant-b")
    assert all(r.tenant_id == "tenant-a" for r in tenant_a)
    assert all(r.tenant_id == "tenant-b" for r in tenant_b)
    assert {r.id for r in tenant_a}.isdisjoint({r.id for r in tenant_b})


async def test_get_health_unknown_resource(provider: SimulatedProvider) -> None:
    report = await provider.get_health("does-not-exist")
    assert report.state == HealthState.UNKNOWN
    assert report.signals == {}


# -- the metric schema (docs/metric-schema.md) -----------------------------


async def test_reports_exactly_the_signals_applicable_to_its_kind(
    provider: SimulatedProvider,
) -> None:
    for tenant in TENANTS:
        for resource in await provider.list_resources(tenant):
            report = await provider.get_health(resource.id)
            assert set(report.signals) == set(applicable_signals(resource.kind)), resource.id


async def test_non_applicable_signals_are_absent_never_zero(
    provider: SimulatedProvider,
) -> None:
    """A worker has no request path and a cache has no replica. Those keys must
    be missing, not present as 0.0 -- absent is null, and null is not zero."""
    worker = await provider.get_health("sim-worker-1")
    assert "request_rate" not in worker.signals
    assert "latency_p95" not in worker.signals
    assert "healthy_target_count" not in worker.signals

    cache = await provider.get_health("sim-cache-1")
    assert "replication_lag_seconds" not in cache.signals

    # The load balancer is the only kind that reports target counts.
    lb = await provider.get_health("sim-lb-1")
    assert "healthy_target_count" in lb.signals
    # gc_pause_ms is testbed-only per the schema, so it is null everywhere.
    assert "gc_pause_ms" not in lb.signals


async def test_every_reported_signal_is_in_the_schema(provider: SimulatedProvider) -> None:
    report = await provider.get_health("sim-web-1")
    assert set(report.signals) <= set(ALL_COLLECTED_SIGNALS)


async def test_the_union_across_kinds_covers_the_schema(provider: SimulatedProvider) -> None:
    """Every signal except the testbed-only one is exercised by some kind, so
    the 25-field list is not carrying dead entries."""
    seen: set[str] = set()
    for tenant in TENANTS:
        for resource in await provider.list_resources(tenant):
            seen |= set((await provider.get_health(resource.id)).signals)
    assert set(ALL_COLLECTED_SIGNALS) - seen == {"gc_pause_ms"}


async def test_error_rates_are_fractions_and_percentages_are_percentages(
    provider: SimulatedProvider,
) -> None:
    """The two metric drafts disagreed by a factor of 100. Error rates are 0-1."""
    report = await provider.get_health("sim-web-1")
    for signal in FRACTION_SIGNALS & set(report.signals):
        assert 0.0 <= report.signals[signal] <= 1.0, signal
    for signal in PERCENT_SIGNALS & set(report.signals):
        assert 0.0 <= report.signals[signal] <= 100.0, signal
    # A healthy service's 5xx rate is a small fraction, nowhere near percent scale.
    assert report.signals["error_rate_5xx"] < 0.1


async def test_health_check_pass_is_binary(provider: SimulatedProvider) -> None:
    report = await provider.get_health("sim-web-1")
    assert report.signals["health_check_pass"] in (0.0, 1.0)


async def test_all_signals_non_negative(provider: SimulatedProvider) -> None:
    report = await provider.get_health("sim-web-1")
    assert all(value >= 0.0 for value in report.signals.values())


# -- clamp-at-zero: latency cannot be exactly 0.0 ---------------------------
#
# `make smoke` caught this for real: sim-cache-1's latency_p50 baseline
# (mean 2.0ms, std 1.0ms) is close enough to 0 that a normal low draw used
# to clamp to exactly 0.0, indistinguishable from "no reading" -- a
# completed request cannot take zero time. See docs/notes/smoke-2026-10-07.md.


def test_positive_floor_covers_exactly_the_three_latency_signals() -> None:
    """The full `_DEFAULT_BASELINE` was audited for this pattern. Only the
    latency percentiles qualify: a completed request cannot take 0ms, but
    e.g. `error_rate_5xx`/`throttle_count` are genuinely 0 whenever nothing
    went wrong, and `replication_lag_seconds` is genuinely 0 when a replica
    is fully caught up -- real zeros, not clamp artifacts."""
    assert set(simulated_module._POSITIVE_FLOOR) == {
        "latency_p50",
        "latency_p95",
        "latency_p99",
    }


async def test_a_deep_low_draw_floors_latency_above_zero_not_at_it(
    monkeypatch: pytest.MonkeyPatch, provider: SimulatedProvider
) -> None:
    """Latency is drawn via `random.lognormvariate` now, not `random.gauss`
    (see `_draw_latency`) -- a real draw can never go this low (it is
    strictly positive by construction), but the floor stays as a safety
    net, so it must still catch a pathologically low value if one ever
    reaches it."""
    monkeypatch.setattr(simulated_module.random, "lognormvariate", lambda mu, sigma: 1e-9)
    # cache's overridden latency baseline (mean 2.0ms) is the one close
    # enough to 0 that this ever mattered in practice.
    report = await provider.get_health("sim-cache-1")
    assert report.signals["latency_p50"] == pytest.approx(0.1)
    assert report.signals["latency_p95"] == pytest.approx(0.1)
    assert report.signals["latency_p99"] == pytest.approx(0.1)
    assert 0.0 not in (
        report.signals["latency_p50"],
        report.signals["latency_p95"],
        report.signals["latency_p99"],
    )


async def test_sim_cache_1_latency_p50_never_piles_up_on_the_floor(
    provider: SimulatedProvider,
) -> None:
    """The regression `make smoke` caught for real: sim-cache-1's
    latency_p50 baseline (mean 2.0ms, std 1.0ms) is the one closest to
    zero, so it is the one most likely to pile up on the floor if the
    latency model ever regresses back towards a normal draw. Seeded so the
    run is reproducible; 5000 ticks is a full seeded run, not a smoke-test
    sample size."""
    random.seed(20261008)
    floor_hits = 0
    for _ in range(5000):
        report = await provider.get_health("sim-cache-1")
        if report.signals["latency_p50"] <= 0.1:
            floor_hits += 1
    assert floor_hits == 0


async def test_a_deep_low_draw_still_floors_other_signals_at_zero(
    monkeypatch: pytest.MonkeyPatch, provider: SimulatedProvider
) -> None:
    """Signals outside `_POSITIVE_FLOOR` are unaffected by this change --
    0.0 is a real possible reading for e.g. `cpu_percent` (idle)."""
    monkeypatch.setattr(simulated_module.random, "gauss", lambda mean, std: -999.0)
    report = await provider.get_health("sim-web-1")
    assert report.signals["cpu_percent"] == 0.0


def test_clamp_floor_does_not_move_a_normal_in_range_value() -> None:
    """The floor only changes the rare low tail -- an ordinary draw well
    above it is returned unchanged, so the mean is unaffected."""
    assert simulated_module._clamp(2.0, math.inf, 0.1) == pytest.approx(2.0)


def test_uptime_seconds_is_canonical_but_not_a_detector_feature() -> None:
    assert "uptime_seconds" in CANONICAL_SIGNALS
    assert "uptime_seconds" not in DETECTOR_SIGNALS
    assert len(DETECTOR_SIGNALS) == 19


# -- uptime behaviour ------------------------------------------------------


async def test_uptime_seconds_grows_with_the_clock(
    provider: SimulatedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    class _Clock:
        value = base

        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return cls.value

    monkeypatch.setattr(simulated_module, "datetime", _Clock)
    first = await provider.get_health("sim-web-1")
    _Clock.value = base + timedelta(seconds=300)
    second = await provider.get_health("sim-web-1")

    assert first.signals["uptime_seconds"] == 0.0
    assert second.signals["uptime_seconds"] == pytest.approx(300.0)


async def test_a_restart_fault_drops_uptime_to_zero(
    provider: SimulatedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drop is the signal -- that is why uptime is collected at all."""
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    class _Clock:
        value = base

        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return cls.value

    monkeypatch.setattr(simulated_module, "datetime", _Clock)
    await provider.get_health("sim-web-1")
    _Clock.value = base + timedelta(seconds=600)
    assert (await provider.get_health("sim-web-1")).signals["uptime_seconds"] > 0

    provider.inject_fault("sim-web-1", "stop", 60)
    assert (await provider.get_health("sim-web-1")).signals["uptime_seconds"] == 0.0

    # And it climbs again from the restart, not from the original boot.
    faults.clear_fault("sim-web-1")
    _Clock.value = base + timedelta(seconds=630)
    assert (await provider.get_health("sim-web-1")).signals["uptime_seconds"] == pytest.approx(30.0)


# -- faults ----------------------------------------------------------------


async def test_cpu_hog_fault_degrades_health_and_spikes_cpu(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "cpu_hog", 60)
    report = await provider.get_health("sim-web-1")
    assert report.state == HealthState.DEGRADED
    assert report.signals["cpu_percent"] > 90.0


async def test_cpu_step_small_is_a_modest_bump(provider: SimulatedProvider) -> None:
    """15 points, inside two sigma of the baseline -- deliberately subtle."""
    provider.inject_fault("sim-web-2", "cpu_step_small", 60)
    report = await provider.get_health("sim-web-2")
    assert report.state == HealthState.DEGRADED
    assert report.signals["cpu_percent"] < 90.0


async def test_cpu_ramp_severity_tracks_intensity(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "cpu_ramp", 60, intensity=0.05)
    low = (await provider.get_health("sim-web-1")).signals["cpu_percent"]
    provider.inject_fault("sim-web-1", "cpu_ramp", 60, intensity=1.0)
    high = (await provider.get_health("sim-web-1")).signals["cpu_percent"]
    assert high > low
    assert high > 85.0


async def test_latency_fault_adds_a_fractional_error_rate(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "latency", 60)
    report = await provider.get_health("sim-web-1")
    assert report.state == HealthState.DEGRADED
    assert report.signals["latency_p99"] > 1000.0
    # +0.05 on a 0-1 scale, NOT +5.
    assert 0.04 < report.signals["error_rate_5xx"] < 0.1


async def test_stop_fault_marks_unhealthy_and_zeroes_signals(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "stop", 60)
    report = await provider.get_health("sim-web-1")
    assert report.state == HealthState.UNHEALTHY
    assert report.signals["health_check_pass"] == 0.0
    assert report.signals["uptime_seconds"] == 0.0
    # A total outage is a 5xx fraction of 1.0, not 100.
    assert report.signals["error_rate_5xx"] == 1.0


async def test_a_fault_never_invents_a_signal_the_kind_lacks(
    provider: SimulatedProvider,
) -> None:
    provider.inject_fault("sim-worker-1", "latency", 60)
    report = await provider.get_health("sim-worker-1")
    assert "latency_p99" not in report.signals
    assert set(report.signals) == set(applicable_signals("worker"))


async def test_region_down_fault_propagates_to_whole_region(provider: SimulatedProvider) -> None:
    # sim-web-1 and sim-db-1 are both in sim-us-east-1.
    provider.inject_fault("sim-web-1", "region_down", 60)
    other = await provider.get_health("sim-db-1")
    assert other.state == HealthState.UNHEALTHY


async def test_region_down_does_not_affect_other_regions(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "region_down", 60)  # sim-us-east-1
    unaffected = await provider.get_health("sim-cache-1")  # sim-ap-south-1
    assert unaffected.state == HealthState.HEALTHY


def test_inject_fault_rejects_unknown_resource(provider: SimulatedProvider) -> None:
    with pytest.raises(KeyError):
        provider.inject_fault("does-not-exist", "cpu_hog", 60)


def test_inject_fault_rejects_unknown_fault_type(provider: SimulatedProvider) -> None:
    with pytest.raises(ValueError, match="unknown fault type"):
        provider.inject_fault("sim-web-1", "nonsense", 60)


async def test_estimate_cost_never_raises_and_has_a_source(provider: SimulatedProvider) -> None:
    from core.models.domain import Action
    from core.models.enums import ActionTier, ActionType

    action = Action(
        tenant_id="tenant-a",
        provider=ProviderName.SIMULATED,
        type=ActionType.SCALE_OUT,
        tier=ActionTier.TIER_2,
        target_resource_id="sim-web-1",
    )
    estimate = await provider.estimate_cost(action)
    assert estimate.source == "static_table"
    assert estimate.one_off_usd >= 0.0


async def test_get_regions_returns_all_three(provider: SimulatedProvider) -> None:
    assert set(await provider.get_regions()) == set(REGIONS)
