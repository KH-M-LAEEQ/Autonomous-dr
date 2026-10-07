"""Cost estimation and the per-tenant budget gate (Week 5, PB-07).

The flow, in order, because the order is the point:

    1. `estimate_cost`      -- price the action from `PricingSource`
    2. `insert_cost_estimate` -- persisted to `cost_estimates` BEFORE the
                                 action runs, so the record exists even if
                                 the gate below refuses it
    3. `check_budget`       -- refuse if this tenant's month-to-date spend,
                                 estimate included, would exceed its cap
    4. `audit_log` entry    -- the reason is always logged, approved or not

Every refused action still has a row in `cost_estimates`: "bad results go in
the table too" (ml/harness/evaluate.py's rule, applied here to spend a
tenant was refused rather than numbers that flattered a detector).
"""

from __future__ import annotations

from core.interfaces.pricing_source import PricingSource
from core.logging import get_logger
from core.models.domain import Action, CostEstimate
from core.repo.audit import append_entry
from core.repo.cost_estimates import insert_cost_estimate, month_to_date_spend_usd
from core.repo.tenants import get_monthly_budget_usd

log = get_logger(__name__)

#: Hours a Tier 1 config action is considered "active" for billing purposes --
#: these are instantaneous control-plane changes, not provisioned resources,
#: so the one-off charge is a few minutes of the SKU's hourly rate, not a
#: full hour. Absent entries fall back to one hour (the conservative default).
_ACTION_DURATION_HOURS: dict[str, float] = {
    "dns_weight_shift": 1 / 60,
    "traffic_reroute": 1 / 60,
    "no_op": 0.0,
}
_DEFAULT_DURATION_HOURS = 1.0


async def estimate_cost(action: Action, region: str, pricing: PricingSource) -> CostEstimate:
    """Price one action. `one_off_usd` is what this specific action costs;
    `projected_monthly_usd` mirrors it (Tier 1 actions are one-shot, not a
    recurring hourly spend) -- it is what the budget gate's cap is compared
    against, by name, in `core/repo/tenants.get_monthly_budget_usd`."""
    sku = action.type.value
    hourly = await pricing.unit_price(action.provider.value, region, sku)
    duration_hours = _ACTION_DURATION_HOURS.get(sku, _DEFAULT_DURATION_HOURS)
    one_off = hourly * duration_hours
    return CostEstimate(
        action_id=action.id,
        one_off_usd=one_off,
        hourly_usd=hourly,
        projected_monthly_usd=one_off,
        confidence=0.4,
        source=pricing.name,
        breakdown={"sku": 1.0, "hourly_usd": hourly, "duration_hours": duration_hours},
    )


def check_budget(estimate: CostEstimate, tenant_id: str) -> tuple[bool, str]:
    """Insert the estimate, then decide. Returns `(approved, reason)`; the
    reason is written to `audit_log` either way, so an approval is as
    traceable as a refusal.

    Must be called exactly once per estimate -- it is what persists the row,
    not a read-only check over one already saved elsewhere.
    """
    insert_cost_estimate(estimate, tenant_id)

    cap = get_monthly_budget_usd(tenant_id)
    spent = month_to_date_spend_usd(tenant_id)  # already includes the row just inserted
    if spent > cap:
        reason = (
            f"month-to-date spend ${spent:.2f} (incl. this ${estimate.one_off_usd:.2f} "
            f"estimate) exceeds tenant cap ${cap:.2f}"
        )
        append_entry(
            actor="core.budget",
            action="action.rejected_by_budget",
            payload={"action_id": str(estimate.action_id), "reason": reason},
            tenant_id=tenant_id,
        )
        return False, reason

    reason = f"month-to-date spend ${spent:.2f} within tenant cap ${cap:.2f}"
    append_entry(
        actor="core.budget",
        action="action.approved_by_budget",
        payload={"action_id": str(estimate.action_id), "reason": reason},
        tenant_id=tenant_id,
    )
    return True, reason
