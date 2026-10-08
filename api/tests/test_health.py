"""Smoke test. If this fails on a clean clone, the scaffold is broken -- fix that first."""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


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
