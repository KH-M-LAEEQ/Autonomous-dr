"""SimulatedExecutor -- Week 5's `ActionExecutor`, Tier 1 only (PB-08).

Implements `core.interfaces.action_executor.ActionExecutor`. Supports exactly
the two Tier 1 action types the interface's own docstring names as Tier 1's
examples: `dns_weight_shift` and `traffic_reroute`. Both are modelled as a
config overwrite on the simulated provider's routing state -- no real
infrastructure changes, so `dry_run`/`execute`/`rollback` can be exercised
freely in tests and in the Week 5 loop alike.

State lives in-process, module-level, mirroring `SimulatedProvider`'s own
`_RESOURCE_BY_ID`/`_BOOT_TIME` pattern: `_ROUTING_STATE` is "what the
simulated provider's routing currently is" per resource, and `_EXECUTED`
is the undo log rollback reads from.

**Idempotent execute, safe-to-call-twice rollback** (the interface's own
contract): both are keyed on `action.id`/`action_id`, converted to `str`
once at the boundary so a `UUID` and its string form are never accidentally
treated as different keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from core.interfaces.action_executor import ActionExecutor
from core.models.domain import Action, ExecutionResult
from core.models.enums import ActionStatus, ActionTier, ActionType
from core.providers.simulated import get_resource

_SUPPORTED_TYPES: frozenset[ActionType] = frozenset(
    {ActionType.DNS_WEIGHT_SHIFT, ActionType.TRAFFIC_REROUTE}
)


@dataclass
class _ExecutedAction:
    resource_id: str
    prior_params: dict[str, object]
    rolled_back: bool = False


#: resource_id -> the params last applied to it. The "simulated provider"
#: routing config this executor's actions overwrite.
_ROUTING_STATE: dict[str, dict[str, object]] = {}
#: str(action.id) -> undo record. Never pruned within a process -- rollback
#: must still work for an action executed long ago, and these are Tier 1
#: config blobs, not telemetry, so there is no volume problem to prune for.
_EXECUTED: dict[str, _ExecutedAction] = {}


class UnsupportedAction(ValueError):
    """Raised by `dry_run`/`execute` for any action type outside Tier 1's
    two supported types -- `supports()` (inherited from `ActionExecutor`)
    is how a caller should have checked first; this is the loud failure for
    a caller that didn't."""


def _check_supported(action: Action) -> None:
    if action.type not in _SUPPORTED_TYPES:
        raise UnsupportedAction(
            f"SimulatedExecutor does not support {action.type.value!r}; "
            f"supported: {sorted(t.value for t in _SUPPORTED_TYPES)}"
        )
    if get_resource(action.target_resource_id) is None:
        raise UnsupportedAction(f"unknown resource {action.target_resource_id!r}")


class SimulatedExecutor(ActionExecutor):
    """Tier 1 executor over `SimulatedProvider`'s resources."""

    name = "simulated"

    @property
    def tier(self) -> ActionTier:
        return ActionTier.TIER_1

    async def dry_run(self, action: Action) -> ExecutionResult:
        """Side-effect free: validates and predicts, touches no state."""
        _check_supported(action)
        now = datetime.now(UTC)
        return ExecutionResult(
            action_id=action.id,
            status=ActionStatus.PROPOSED,
            started_at=now,
            finished_at=now,
            provider_ref=None,
        )

    async def execute(self, action: Action) -> ExecutionResult:
        """Idempotent on `action.id`: calling this twice for the same action
        applies the params once and returns the same success result both
        times, rather than re-applying (which would also clobber the undo
        record's `prior_params` with the already-applied state)."""
        _check_supported(action)
        key = str(action.id)
        now = datetime.now(UTC)

        if key not in _EXECUTED:
            prior = dict(_ROUTING_STATE.get(action.target_resource_id, {}))
            _ROUTING_STATE[action.target_resource_id] = dict(action.params)
            _EXECUTED[key] = _ExecutedAction(
                resource_id=action.target_resource_id, prior_params=prior
            )

        return ExecutionResult(
            action_id=action.id,
            status=ActionStatus.SUCCEEDED,
            started_at=now,
            finished_at=now,
            provider_ref=f"sim-exec-{action.id}",
            rollback_token=key,
        )

    async def rollback(self, action_id: str) -> ExecutionResult:
        """Safe to call twice: the second call finds `rolled_back` already
        `True` and just re-reports success without touching `_ROUTING_STATE`
        again (which would otherwise restore an already-restored resource to
        whatever a THIRD action did to it in between -- a real double-undo
        bug, not a hypothetical one)."""
        now = datetime.now(UTC)
        key = str(action_id)
        record = _EXECUTED.get(key)
        if record is None:
            raise KeyError(f"no executed action to rollback for {action_id!r}")

        if not record.rolled_back:
            if record.prior_params:
                _ROUTING_STATE[record.resource_id] = record.prior_params
            else:
                _ROUTING_STATE.pop(record.resource_id, None)
            record.rolled_back = True

        return ExecutionResult(
            action_id=UUID(key),
            status=ActionStatus.ROLLED_BACK,
            started_at=now,
            finished_at=now,
        )


def current_routing_state(resource_id: str) -> dict[str, object] | None:
    """Test/inspection hook: what `SimulatedExecutor` currently has applied
    to this resource, or `None` if nothing has (or nothing undone has)."""
    return _ROUTING_STATE.get(resource_id)
