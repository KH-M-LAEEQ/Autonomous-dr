"""Tests for core/decision/engine.py (PB-06). Needs a real Postgres -- see
core/tests/conftest.py."""

from __future__ import annotations

import pytest

from core.db import ping

if not ping():
    pytest.skip(
        "Postgres is unreachable -- start it with `make up && make migrate`",
        allow_module_level=True,
    )

from core.decision.engine import (
    CANDIDATE_TYPES,
    WEIGHTS,
    build_terms,
    decide,
)
from core.decision.utility import score
from core.incidents import open_incident
from core.models.domain import Action
from core.models.enums import ActionTier, ActionType, ProviderName
from core.pricing import StaticPriceTable
from core.repo.decisions import get_decision_record
from core.tests.conftest import MakeDbTenant, resource_id_for

PRICING = StaticPriceTable()


def _candidate(tenant_id: str, action_type: ActionType = ActionType.DNS_WEIGHT_SHIFT) -> Action:
    return Action(
        tenant_id=tenant_id,
        provider=ProviderName.SIMULATED,
        type=action_type,
        tier=ActionTier.TIER_1,
        target_resource_id=resource_id_for(tenant_id),
    )


async def test_decide_persists_a_decision_choosing_a_real_candidate(
    make_db_tenant: MakeDbTenant,
) -> None:
    tenant_id = make_db_tenant(budget_usd=25.0)
    incident_id = open_incident(tenant_id, resource_id_for(tenant_id))

    decision = await decide(incident_id, tenant_id, resource_id_for(tenant_id), PRICING)

    assert decision.incident_id == incident_id
    assert decision.chosen_action is not None
    assert decision.chosen_action.type in CANDIDATE_TYPES
    assert decision.weights == WEIGHTS
    assert len(decision.rejected) == len(CANDIDATE_TYPES) - 1

    record = get_decision_record(decision.id)
    assert record is not None
    assert record["chosen_action_id"] is not None


async def test_higher_cost_never_raises_the_score(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant(budget_usd=25.0)
    cheap_terms = await build_terms(_candidate(tenant_id), "sim-us-east-1", 25.0, PRICING)
    # A tiny cap makes the SAME action's cost term relatively much larger.
    expensive_terms = await build_terms(_candidate(tenant_id), "sim-us-east-1", 0.001, PRICING)

    assert expensive_terms["cost"] > cheap_terms["cost"]
    assert score(expensive_terms, WEIGHTS) <= score(cheap_terms, WEIGHTS)


async def test_higher_safety_never_lowers_the_score(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant(budget_usd=25.0)
    tier1_action = _candidate(tenant_id)
    tier2_action = tier1_action.model_copy(update={"tier": ActionTier.TIER_2})

    safer_terms = await build_terms(tier1_action, "sim-us-east-1", 25.0, PRICING)
    riskier_terms = await build_terms(tier2_action, "sim-us-east-1", 25.0, PRICING)

    assert safer_terms["safety"] > riskier_terms["safety"]
    assert score(safer_terms, WEIGHTS) >= score(riskier_terms, WEIGHTS)


async def test_a_saved_decision_can_be_rescored_from_its_own_record(
    make_db_tenant: MakeDbTenant,
) -> None:
    tenant_id = make_db_tenant(budget_usd=25.0)
    incident_id = open_incident(tenant_id, resource_id_for(tenant_id))
    decision = await decide(incident_id, tenant_id, resource_id_for(tenant_id), PRICING)

    record = get_decision_record(decision.id)
    assert record is not None
    rescored = score(dict(record["terms"]), dict(record["weights"]))

    assert rescored == pytest.approx(record["utility"])
    assert rescored == pytest.approx(decision.utility)
