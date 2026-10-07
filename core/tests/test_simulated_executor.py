"""Tests for core/providers/simulated_executor.py (PB-08). Pure in-process
state -- no Postgres needed."""

from __future__ import annotations

import pytest

from core.models.domain import Action, ExecutionResult
from core.models.enums import ActionStatus, ActionTier, ActionType, ProviderName
from core.providers.simulated_executor import (
    SimulatedExecutor,
    UnsupportedAction,
    current_routing_state,
)

EXECUTOR = SimulatedExecutor()


def _token(result: ExecutionResult) -> str:
    """`rollback_token` is `str | None` on the shared `ExecutionResult`
    shape; every caller here knows (from just having executed the action)
    that it is set, so this is where that knowledge becomes a real `str`."""
    assert result.rollback_token is not None
    return result.rollback_token


def _action(
    action_type: ActionType = ActionType.DNS_WEIGHT_SHIFT,
    target: str = "sim-web-1",
    params: dict[str, object] | None = None,
) -> Action:
    return Action(
        tenant_id="tenant-a",
        provider=ProviderName.SIMULATED,
        type=action_type,
        tier=ActionTier.TIER_1,
        target_resource_id=target,
        params=params or {"weights": {"sim-us-east-1": 0.8, "sim-eu-west-1": 0.2}},
    )


async def test_tier_is_tier_1() -> None:
    assert EXECUTOR.tier == ActionTier.TIER_1


async def test_supports_matches_the_interfaces_tier_rule() -> None:
    assert EXECUTOR.supports(_action()) is True
    tier2_action = _action(ActionType.SCALE_OUT)
    assert EXECUTOR.supports(tier2_action) is True  # supports() only checks tier ordering


async def test_dry_run_is_side_effect_free() -> None:
    action = _action(target="sim-db-1")
    result = await EXECUTOR.dry_run(action)
    assert result.status == ActionStatus.PROPOSED
    assert current_routing_state("sim-db-1") is None


async def test_dry_run_rejects_an_unsupported_action_type() -> None:
    with pytest.raises(UnsupportedAction):
        await EXECUTOR.dry_run(_action(ActionType.SCALE_OUT))


async def test_execute_applies_params_to_the_target_resource() -> None:
    action = _action(target="sim-cache-1", params={"weights": {"sim-ap-south-1": 1.0}})
    result = await EXECUTOR.execute(action)
    assert result.status == ActionStatus.SUCCEEDED
    assert current_routing_state("sim-cache-1") == {"weights": {"sim-ap-south-1": 1.0}}


async def test_execute_is_idempotent_on_action_id() -> None:
    action = _action(target="sim-web-2", params={"weights": {"a": 1.0}})
    first = await EXECUTOR.execute(action)
    second = await EXECUTOR.execute(action)
    assert first.status == second.status == ActionStatus.SUCCEEDED
    assert current_routing_state("sim-web-2") == {"weights": {"a": 1.0}}


async def test_every_action_can_be_undone() -> None:
    """The headline guarantee: whatever execute() changed, rollback()
    restores -- including back to "nothing was ever applied"."""
    target = "sim-worker-1"
    assert current_routing_state(target) is None

    action = _action(target=target, params={"route": "region-b"})
    executed = await EXECUTOR.execute(action)
    assert current_routing_state(target) == {"route": "region-b"}

    rolled_back = await EXECUTOR.rollback(_token(executed))
    assert rolled_back.status == ActionStatus.ROLLED_BACK
    assert current_routing_state(target) is None


async def test_rollback_restores_the_prior_value_not_just_clears_it() -> None:
    target = "sim-lb-1"
    first = _action(target=target, params={"route": "region-a"})
    await EXECUTOR.execute(first)

    second = _action(target=target, params={"route": "region-b"})
    executed_second = await EXECUTOR.execute(second)
    assert current_routing_state(target) == {"route": "region-b"}

    await EXECUTOR.rollback(_token(executed_second))
    assert current_routing_state(target) == {"route": "region-a"}


async def test_rollback_is_safe_to_call_twice() -> None:
    target = "sim-db-2"
    action = _action(target=target, params={"route": "region-c"})
    executed = await EXECUTOR.execute(action)

    first = await EXECUTOR.rollback(_token(executed))
    second = await EXECUTOR.rollback(_token(executed))
    assert first.status == second.status == ActionStatus.ROLLED_BACK
    assert current_routing_state(target) is None


async def test_rollback_of_an_action_never_executed_raises() -> None:
    with pytest.raises(KeyError):
        await EXECUTOR.rollback("00000000-0000-0000-0000-000000000000")


async def test_execute_rejects_an_unknown_resource() -> None:
    with pytest.raises(UnsupportedAction):
        await EXECUTOR.execute(_action(target="no-such-resource"))
