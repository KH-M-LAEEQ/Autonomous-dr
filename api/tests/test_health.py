"""Smoke test. If this fails on a clean clone, the scaffold is broken -- fix that first."""

import pytest
from fastapi.testclient import TestClient

import api.routers.health as health_module
from api.main import app
from core.interfaces.cloud_provider import CloudProvider
from core.models.domain import Action, CostEstimate, HealthReport, Resource
from core.models.enums import ProviderName

client = TestClient(app)


class _RaisingProvider(CloudProvider):
    """A CloudProvider stub whose list_resources always raises -- stands in
    for a real provider that's down, to prove /ready survives it. The
    other abstract methods are never called by this test; they exist only
    to satisfy the frozen interface."""

    name = ProviderName.SIMULATED

    async def get_health(self, resource_id: str) -> HealthReport:
        raise NotImplementedError

    async def list_resources(self, tenant_id: str) -> list[Resource]:
        raise RuntimeError("provider is down")

    async def estimate_cost(self, action: Action) -> CostEstimate:
        raise NotImplementedError

    async def execute(self, action: Action) -> str:
        raise NotImplementedError

    async def get_regions(self) -> list[str]:
        raise NotImplementedError


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_schema_generates() -> None:
    """Guards the frontend contract: if this breaks, the mock server breaks."""
    schema = app.openapi()
    assert "/api/v1/incidents" in schema["paths"]


def test_ready_reports_dependencies() -> None:
    """Passes with databases down -- it just reports false. That is intentional."""
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ready", "postgres", "influxdb", "config", "detector_fitted"}
    # Whether Postgres happens to be reachable in this test environment or
    # not, the field itself must always be present, always a bool-valued
    # mapping, and must never make /ready itself fail (core/detector_state.
    # is_fitted() fails safe to False rather than raising).
    assert isinstance(body["detector_fitted"], dict)
    assert all(isinstance(v, bool) for v in body["detector_fitted"].values())


async def test_fitted_for_provider_returns_empty_without_raising_when_list_resources_fails() -> (
    None
):
    result = await health_module._fitted_for_provider(_RaisingProvider(), "tenant-a")
    assert result == {}


def test_ready_never_500s_when_a_provider_raises_listing_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The actual requirement: /ready as a whole, not just the helper in
    isolation, must stay a 200 when a provider's list_resources raises --
    and detector_fitted simply carries no entries for that provider."""
    monkeypatch.setattr(health_module, "enabled_providers", lambda: [_RaisingProvider()])
    monkeypatch.setattr(health_module, "list_active_tenant_ids", lambda: ["tenant-a"])

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["detector_fitted"] == {}
