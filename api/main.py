"""FastAPI application.

The OpenAPI schema this produces IS the frontend contract (Week 2 deliverable).
Export it with:  make api  then  curl localhost:8000/openapi.json > docs/api/openapi.json
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import actions, health, incidents, resources, ws
from core.config import get_settings
from core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    log.info(
        "starting api env=%s detector=%s consensus=%s executor=%s providers=%s",
        settings.app_env,
        settings.detector,
        settings.consensus,
        settings.executor,
        settings.enabled_providers,
    )
    yield
    log.info("api stopped")


app = FastAPI(
    title="AutonomousDR API",
    version="0.1.0",
    description="Autonomous multi-cloud disaster recovery -- UCP FYP 2026-27",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(resources.router)
app.include_router(incidents.router)
app.include_router(actions.router)
app.include_router(ws.router)
