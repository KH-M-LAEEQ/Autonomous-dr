"""Resource inventory. Week 3 (simulated) / Week 7 (AWS) / Week 9 (Azure)."""

from fastapi import APIRouter

from core.models.domain import Resource
from core.providers import enabled_providers

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


@router.get("", response_model=list[Resource])
async def list_resources(tenant_id: str = "tenant-a") -> list[Resource]:
    """Every resource across every enabled provider for one tenant."""
    resources: list[Resource] = []
    for provider in enabled_providers():
        resources.extend(await provider.list_resources(tenant_id))
    return resources
