"""Liveness and readiness. The only endpoints implemented in Week 1."""

from fastapi import APIRouter
from pydantic import BaseModel

from core import __version__, db, influx
from core.config import get_settings

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
    """
    s = get_settings()
    pg = db.ping()
    ifx = influx.ping()
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
    )
