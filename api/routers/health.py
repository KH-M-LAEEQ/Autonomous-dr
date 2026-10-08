"""Liveness and readiness. The only endpoints implemented in Week 1."""

from fastapi import APIRouter
from pydantic import BaseModel

from core import __version__, db, influx
from core.config import get_settings
from core.detector_state import is_fitted
from core.providers import enabled_providers
from core.repo.tenants import list_active_tenant_ids

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


class ReadyResponse(BaseModel):
    ready: bool
    postgres: bool
    influxdb: bool
    config: dict[str, str]
    detector_fitted: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness. Never touches a dependency, so it stays up during an outage."""
    s = get_settings()
    return HealthResponse(status="ok", version=__version__, env=s.app_env)


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Readiness. Checks every dependency and reports which implementations are live.

    If this returns ready=false on a teammate's machine, the answer is almost
    always `make up`.

    `detector_fitted` is read-only and never affects `ready`: it is
    cross-process visibility into `ml.tasks`' per-resource fit state (that
    task runs in the Celery worker/beat process, not here -- see
    `core/detector_state.py`), added so `scripts/smoke.py` can poll for a
    resource's detector warming up instead of guessing a fixed sleep.
    """
    s = get_settings()
    pg = db.ping()
    ifx = influx.ping()
    fitted: dict[str, bool] = {}
    for provider in enabled_providers():
        for tenant_id in list_active_tenant_ids():
            for resource in await provider.list_resources(tenant_id):
                fitted[resource.id] = is_fitted(resource.id)
    return ReadyResponse(
        ready=pg and ifx,
        postgres=pg,
        influxdb=ifx,
        config={
            "detector": s.detector,
            "consensus": s.consensus,
            "executor": s.executor,
            "explainer": s.explainer,
            "providers": ",".join(s.enabled_providers),
        },
        detector_fitted=fitted,
    )
