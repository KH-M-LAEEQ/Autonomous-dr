"""Telemetry collector (Week 3).

Polls every enabled `CloudProvider`, for every active tenant, every resource,
every 10 seconds (core/tasks.py beat schedule) -- and writes one point per
resource into InfluxDB tagged with tenant/region/resource/provider so every
later query (the dashboard, the detector, the evaluation harness) can filter
on any of those without a join.

Running uninterrupted from Week 3 is the point: the dataset accumulates
while nobody is watching, which is what makes Week 10 training easy. Do not
add a "pause collection" switch.
"""

from __future__ import annotations

from core import influx
from core.interfaces.cloud_provider import CloudProvider
from core.logging import get_logger
from core.models.domain import Resource
from core.providers import enabled_providers
from core.repo.resources import upsert_resource
from core.repo.tenants import list_active_tenant_ids

log = get_logger(__name__)

MEASUREMENT = "telemetry"


async def _poll_resource(provider: CloudProvider, resource: Resource) -> None:
    upsert_resource(resource)
    report = await provider.get_health(resource.id)
    if not report.signals:
        return
    # `report.signals` carries only the signals this resource actually reports
    # -- up to all 25 of core/signals.ALL_COLLECTED_SIGNALS, fewer when some do
    # not apply to its kind. Those are absent rather than 0.0, and passing the
    # dict through unchanged is what preserves that: InfluxDB has no null, so a
    # field that is never written reads back as null, which is the intended
    # meaning. Never fill a gap with 0.0 here -- that would record a
    # measurement claiming the value really is zero.
    influx.write_metrics(
        measurement=MEASUREMENT,
        tags={
            "tenant_id": resource.tenant_id,
            "region": resource.region,
            "resource_id": resource.id,
            "provider": provider.name.value,
            "kind": resource.kind,
        },
        fields=report.signals,
        # A field, not a tag -- see write_metrics's docstring. health_state
        # changes on nearly every write once a fault lands (healthy ->
        # degraded), and nothing queries it as a filterable dimension
        # (grepped: write-only before this), so there is no reason for it
        # to be part of this resource's series identity.
        string_fields={"health_state": report.state.value},
        timestamp=report.observed_at,
    )


async def poll_all_providers() -> int:
    """One collection cycle across every enabled provider and active tenant.

    Returns the number of resources polled -- used by the beat task's log
    line and by tests, not by any control-flow decision.
    """
    count = 0
    for provider in enabled_providers():
        for tenant_id in list_active_tenant_ids():
            resources = await provider.list_resources(tenant_id)
            for resource in resources:
                await _poll_resource(provider, resource)
                count += 1
    return count
