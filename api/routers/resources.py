"""Resource inventory. Week 3 (simulated) / Week 7 (AWS) / Week 9 (Azure)."""

from fastapi import APIRouter

from core.models.domain import Resource

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


@router.get("", response_model=list[Resource])
async def list_resources(tenant_id: str = "tenant-a") -> list[Resource]:
    """Every resource across every enabled provider for one tenant.

    Week 3 wires this to the provider registry. Returns [] until then so the
    frontend can build against a real shape from day one.
    """
    return []
