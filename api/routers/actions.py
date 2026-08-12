"""Actions, plus the demo-critical fault injection endpoint (Week 6)."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from core.models.domain import Action

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
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Week 3")
