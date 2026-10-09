"""Actions, plus the demo-critical fault injection endpoint."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from core.config import get_settings
from core.models.domain import Action
from core.providers import get_provider
from core.providers.simulated import SimulatedProvider

router = APIRouter(prefix="/api/v1", tags=["actions"])


class FaultInjectionRequest(BaseModel):
    """Drives the dashboard's fault button. Keep this stable -- your demo depends on it."""

    resource_id: str
    fault_type: str  # cpu_hog | latency | stop | pause | region_down
    duration_seconds: int = 120


@router.get("/actions", response_model=list[Action])
async def list_actions(incident_id: str | None = None) -> list[Action]:
    return []


@router.post("/faults", status_code=status.HTTP_202_ACCEPTED)
async def inject_fault(req: FaultInjectionRequest) -> dict[str, str]:
    """Inject a fault into the simulator. Only ever enabled against SimulatedProvider."""
    if "simulated" not in get_settings().enabled_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fault injection requires the simulated provider to be enabled",
        )
    provider = get_provider("simulated")
    assert isinstance(provider, SimulatedProvider)
    try:
        provider.inject_fault(req.resource_id, req.fault_type, req.duration_seconds)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"resource_id": req.resource_id, "fault_type": req.fault_type, "status": "injected"}
