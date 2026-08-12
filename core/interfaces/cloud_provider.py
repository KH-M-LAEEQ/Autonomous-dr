"""FROZEN INTERFACE 1 of 5 -- CloudProvider.

Implemented by: SimulatedProvider (W3), AWSProvider (W7), AzureProvider (W9),
GCPProvider (W21). Terraform is an ActionExecutor, not a provider -- it does not
report health.

Designed so that adding a fourth cloud is a new file, never an edit to an
existing one.
"""

from abc import ABC, abstractmethod

from core.models.domain import Action, CostEstimate, HealthReport, Resource
from core.models.enums import ProviderName


class CloudProvider(ABC):
    """Read-and-price surface of one cloud. Mutating the cloud is ActionExecutor's job.

    Implementations must be safe to call every 10 seconds from the collector and
    must never raise on transient network failure -- return UNKNOWN health instead.
    """

    name: ProviderName

    @abstractmethod
    async def get_health(self, resource_id: str) -> HealthReport:
        """Current health of one resource. Never raises on transient failure."""
        ...

    @abstractmethod
    async def list_resources(self, tenant_id: str) -> list[Resource]:
        """Every resource this provider manages for one tenant."""
        ...

    @abstractmethod
    async def estimate_cost(self, action: Action) -> CostEstimate:
        """Price an action BEFORE it runs. Must return a value, never None --
        fall back to the static table if the live pricing API is unreachable."""
        ...

    @abstractmethod
    async def execute(self, action: Action) -> str:
        """Low-level provider call. Returns a provider reference (ARN, operation id).

        Do not call this directly from the decision path -- go through
        ActionExecutor so dry-run, tiering and rollback are enforced.
        """
        ...

    @abstractmethod
    async def get_regions(self) -> list[str]:
        """Regions available to this account, for failover target selection."""
        ...
