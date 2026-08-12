"""FROZEN INTERFACE 4 of 5 -- ActionExecutor.

Implemented by: SimulatedExecutor (W5), AWSExecutor (W12), AzureExecutor,
GCPExecutor (W21), TerraformExecutor (W20).
"""

from abc import ABC, abstractmethod

from core.models.domain import Action, ExecutionResult
from core.models.enums import TIER_ORDER, ActionTier


class ActionExecutor(ABC):
    """The only component permitted to change real infrastructure.

    Contract:
      * `dry_run` must be side-effect free and is mandatory before first live use
        of any new action type.
      * `execute` must be idempotent on `action.id` -- a retried task must not
        fail over twice.
      * Every action type must have a working `rollback`. No rollback, no Tier 2+.
      * Tier 3 requires recorded human approval before execute is called.
    """

    name: str

    @property
    @abstractmethod
    def tier(self) -> ActionTier:
        """Highest tier this executor is allowed to perform."""
        ...

    @abstractmethod
    async def dry_run(self, action: Action) -> ExecutionResult:
        """Validate and predict without touching anything."""
        ...

    @abstractmethod
    async def execute(self, action: Action) -> ExecutionResult:
        """Perform the action. Idempotent on action.id."""
        ...

    @abstractmethod
    async def rollback(self, action_id: str) -> ExecutionResult:
        """Undo a previously executed action. Must be safe to call twice."""
        ...

    def supports(self, action: Action) -> bool:
        """Whether this executor can handle the action at its permitted tier."""
        return TIER_ORDER[action.tier] <= TIER_ORDER[self.tier]
