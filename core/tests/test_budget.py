"""Tests for core/budget.py (PB-07): static pricing, cost estimate, budget
gate. Needs a real Postgres -- see core/tests/conftest.py."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db import ping, session_scope

if not ping():
    pytest.skip(
        "Postgres is unreachable -- start it with `make up && make migrate`",
        allow_module_level=True,
    )

from core.budget import check_budget, estimate_cost
from core.models.domain import Action
from core.models.enums import ActionTier, ActionType, ProviderName
from core.pricing import StaticPriceTable
from core.repo.actions import insert_action
from core.tests.conftest import MakeDbTenant, resource_id_for

PRICING = StaticPriceTable()


def _dns_shift_action(tenant_id: str) -> Action:
    action = Action(
        tenant_id=tenant_id,
        provider=ProviderName.SIMULATED,
        type=ActionType.DNS_WEIGHT_SHIFT,
        tier=ActionTier.TIER_1,
        target_resource_id=resource_id_for(tenant_id),
        params={"weights": {"sim-us-east-1": 0.5, "sim-eu-west-1": 0.5}},
    )
    insert_action(action)
    return action


async def test_static_price_table_prices_a_known_sku() -> None:
    price = await PRICING.unit_price("simulated", "sim-us-east-1", "dns_weight_shift")
    assert price > 0.0


async def test_static_price_table_is_always_available() -> None:
    assert await PRICING.is_available() is True


async def test_estimate_cost_is_tiny_for_a_tier_1_config_change() -> None:
    action = Action(
        tenant_id="tenant-a",
        provider=ProviderName.SIMULATED,
        type=ActionType.DNS_WEIGHT_SHIFT,
        tier=ActionTier.TIER_1,
        target_resource_id="sim-web-1",
    )
    estimate = await estimate_cost(action, "sim-us-east-1", PRICING)
    assert estimate.action_id == action.id
    assert 0.0 < estimate.one_off_usd < 1.0
    assert estimate.source == "static_table"


async def test_under_cap_action_is_approved(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant(budget_usd=25.0)
    action = _dns_shift_action(tenant_id)
    estimate = await estimate_cost(action, "sim-us-east-1", PRICING)

    approved, reason = check_budget(estimate, tenant_id)

    assert approved is True
    assert "within tenant cap" in reason


async def test_over_cap_action_is_refused(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant(budget_usd=0.001)
    action = _dns_shift_action(tenant_id)
    estimate = await estimate_cost(action, "sim-us-east-1", PRICING)

    approved, reason = check_budget(estimate, tenant_id)

    assert approved is False
    assert "exceeds tenant cap" in reason


async def test_refusal_reason_is_logged_in_audit_log(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant(budget_usd=0.001)
    action = _dns_shift_action(tenant_id)
    estimate = await estimate_cost(action, "sim-us-east-1", PRICING)

    _approved, reason = check_budget(estimate, tenant_id)

    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT action, payload FROM audit_log "
                "WHERE tenant_id = :tenant_id AND action = 'action.rejected_by_budget'"
            ),
            {"tenant_id": tenant_id},
        ).first()
    assert row is not None
    assert row.payload["reason"] == reason
    assert row.payload["action_id"] == str(action.id)


async def test_estimate_is_saved_even_when_refused(make_db_tenant: MakeDbTenant) -> None:
    """PB-07: the estimate is written BEFORE the action runs, regardless of
    what the gate decides -- a refused action still has its cost on record."""
    tenant_id = make_db_tenant(budget_usd=0.001)
    action = _dns_shift_action(tenant_id)
    estimate = await estimate_cost(action, "sim-us-east-1", PRICING)

    check_budget(estimate, tenant_id)

    with session_scope() as session:
        row = session.execute(
            text("SELECT action_id FROM cost_estimates WHERE action_id = :action_id"),
            {"action_id": str(action.id)},
        ).first()
    assert row is not None


async def test_second_action_same_month_adds_to_the_running_total(
    make_db_tenant: MakeDbTenant,
) -> None:
    """The cap is a MONTHLY total, not a per-action ceiling: two cheap
    actions that individually fit can still combine to exceed it.

    The cap is set to exactly one action's cost (not e.g. 1.5x it) because
    `monthly_budget_usd` is `NUMERIC(12, 2)` -- cents precision -- and this
    SKU's one-off cost is itself a whole cent ($0.01); a 1.5x cap would be
    $0.015, which Postgres rounds to $0.02 on insert and silently changes
    what's being tested.
    """
    one_off = (
        await estimate_cost(
            Action(
                tenant_id="tenant-a",
                provider=ProviderName.SIMULATED,
                type=ActionType.DNS_WEIGHT_SHIFT,
                tier=ActionTier.TIER_1,
                target_resource_id="sim-web-1",
            ),
            "sim-us-east-1",
            PRICING,
        )
    ).one_off_usd
    tenant_id = make_db_tenant(budget_usd=one_off)

    first = _dns_shift_action(tenant_id)
    first_estimate = await estimate_cost(first, "sim-us-east-1", PRICING)
    first_ok, _ = check_budget(first_estimate, tenant_id)

    second = _dns_shift_action(tenant_id)
    second_estimate = await estimate_cost(second, "sim-us-east-1", PRICING)
    second_ok, reason = check_budget(second_estimate, tenant_id)

    assert first_ok is True
    assert second_ok is False
    assert "exceeds tenant cap" in reason
