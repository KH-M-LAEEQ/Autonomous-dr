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
    assert set(body) == {"ready", "postgres", "influxdb", "config"}
