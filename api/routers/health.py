"""Liveness and readiness. The only endpoints implemented in Week 1."""

from fastapi import APIRouter
from pydantic import BaseModel

from core import __version__, db, influx
from core.config import get_settings
from core.detector_state import is_fitted
from core.interfaces.cloud_provider import CloudProvider
from core.logging import get_logger
from core.providers import enabled_providers
from core.repo.tenants import list_active_tenant_ids

log = get_logger(__name__)

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


async def _fitted_for_provider(provider: CloudProvider, tenant_id: str) -> dict[str, bool]:
    """`detector_fitted` entries for one provider/tenant, never raising.

    `list_resources` is the one call here that reaches outside this
    process (a real provider in a later week would be a network call);
    `/ready` must stay a 200 regardless of what it does. An exception
    here means this provider's resources are simply absent from the
    returned mapping -- `scripts/smoke.py`'s `.get(resource_id, False)`
    already treats an absent entry as "not fitted", so the caller doesn't
    need a separate "and mark it False" step for resources it never even
    learned the ids of.
    """
    try:
        resources = await provider.list_resources(tenant_id)
    except Exception:
        log.warning(
            "list_resources failed for provider=%s tenant=%s; reporting no "
            "detector_fitted entries for it",
            provider.name,
            tenant_id,
            exc_info=True,
        )
        return {}
    return {resource.id: is_fitted(resource.id) for resource in resources}


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Readiness. Checks every dependency and reports which implementations are live.

    If this returns ready=false on a teammate's machine, the answer is almost
    always `make up`.

    `detector_fitted` is read-only and never affects `ready`: it is
    cross-process visibility into `ml.tasks`' per-resource fit state (that
    task runs in the Celery worker/beat process, not here -- see
    `core/detector_state.py`), added so `scripts/smoke.py` can poll for a
    resource's detector warming up instead of guessing a fixed sleep. A
    provider that raises while listing its resources (see
    `_fitted_for_provider`) must never turn into a 500 here.
    """
    s = get_settings()
    pg = db.ping()
    ifx = influx.ping()
    fitted: dict[str, bool] = {}
    for provider in enabled_providers():
        for tenant_id in list_active_tenant_ids():
            fitted.update(await _fitted_for_provider(provider, tenant_id))
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
