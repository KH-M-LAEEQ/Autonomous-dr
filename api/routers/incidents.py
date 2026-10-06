"""Incident feed and detail view."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from core.incidents import get_incident as repo_get_incident
from core.incidents import list_incidents as repo_list_incidents
from core.models.domain import Incident

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=list[Incident])
async def list_incidents(tenant_id: str = "tenant-a", limit: int = 50) -> list[Incident]:
    """Most recent incidents first. Powers the live incident list."""
    return [Incident(**row) for row in repo_list_incidents(tenant_id, limit)]


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: UUID) -> Incident:
    """Basic incident fields for now -- detections/decision/votes/actions/
    explanation join in once those tables have writers (Week 5+)."""
    row = repo_get_incident(incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident not found")
    return Incident(**row)
