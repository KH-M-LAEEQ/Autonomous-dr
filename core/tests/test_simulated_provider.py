"""Tests for core/providers/simulated.py.

Fault state is backed by Redis in production (core/faults.py), so these
monkeypatch `core.faults` with an in-memory dict -- the provider's own logic
is what's under test here, not Redis.
"""

from __future__ import annotations

import pytest

from core import faults
from core.models.enums import HealthState, ProviderName
from core.providers.simulated import REGIONS, TENANTS, SimulatedProvider


@pytest.fixture(autouse=True)
def fake_fault_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    store: dict[str, str] = {}
    monkeypatch.setattr(faults, "set_fault", lambda rid, ft, dur: store.__setitem__(rid, ft))
    monkeypatch.setattr(faults, "get_fault", lambda rid: store.get(rid))
    monkeypatch.setattr(faults, "clear_fault", lambda rid: store.pop(rid, None))
    return store


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


async def test_get_health_reports_all_20_signals(provider: SimulatedProvider) -> None:
    report = await provider.get_health("sim-web-1")
    assert report.state == HealthState.HEALTHY
    assert len(report.signals) == 20
    assert all(value >= 0.0 for value in report.signals.values())


async def test_cpu_hog_fault_degrades_health_and_spikes_cpu(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "cpu_hog", 60)
    report = await provider.get_health("sim-web-1")
    assert report.state == HealthState.DEGRADED
    assert report.signals["cpu_pct"] > 90.0


async def test_stop_fault_marks_unhealthy_and_zeroes_signals(provider: SimulatedProvider) -> None:
    provider.inject_fault("sim-web-1", "stop", 60)
    report = await provider.get_health("sim-web-1")
    assert report.state == HealthState.UNHEALTHY
    assert report.signals["uptime_pct"] == 0.0
    assert report.signals["error_rate_pct"] == 100.0


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
