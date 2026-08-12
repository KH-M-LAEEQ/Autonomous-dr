"""Incident feed and detail view. Week 4 implements the lifecycle behind this."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from core.models.domain import Incident

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=list[Incident])
async def list_incidents(tenant_id: str = "tenant-a", limit: int = 50) -> list[Incident]:
    """Most recent incidents first. Powers the live incident list."""
    return []


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: UUID) -> Incident:
    """Full incident detail: detections, decision, votes, actions, explanation."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Week 4")
