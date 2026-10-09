"""The Week 5 decision engine (PB-06).

For one incident: build a small set of Tier 1 candidate actions, price and
score each one with `core.decision.utility.score`, and persist the winner as
a validated `Decision`. Only `ability` is a stub here (1.0 for every
candidate, per the spec -- the Week 3 collector has no history yet for a
real capability score); `cost`, `latency` and `safety` are all real,
if simple, numbers:

  * `cost`    = this candidate's priced `projected_monthly_usd`, divided by
                the tenant's monthly cap -- so a candidate that alone would
                blow the whole budget scores a full 1.0 (the worst a
                normalised term can be), not some value above it.
  * `latency` = a static per-action-type recovery estimate, divided by 60s
                (ADR-0011's own normalisation unit for this term).
  * `safety`  = a static per-tier reversibility score. Tier 1 is reversible
                in seconds (ActionTier's own docstring), so it is rated the
                safest; higher tiers drop as rollback gets slower and riskier.

The formula itself (signs, required terms, [0,1]/sum-to-1 validation) lives
in `core/decision/utility.py` and is never duplicated here.
"""

from __future__ import annotations

from uuid import UUID

from core.budget import estimate_cost
from core.decision.utility import score
from core.interfaces.pricing_source import PricingSource
from core.models.domain import Action, Decision
from core.models.enums import ActionTier, ActionType, ProviderName
from core.repo.actions import insert_action
from core.repo.decisions import insert_decision
from core.repo.resources import get_resource_record
from core.repo.tenants import get_monthly_budget_usd

#: W5's weights (ADR-0011's worked example): ability .20, cost .25,
#: latency .25, safety .30.
WEIGHTS: dict[str, float] = {"ability": 0.20, "cost": 0.25, "latency": 0.25, "safety": 0.30}
FORMULA_VERSION = "w5-v1"

#: The only two action types `SimulatedExecutor` (PB-08) can actually run --
#: a decision that picked a type nothing can execute would be a decision
#: that goes nowhere.
CANDIDATE_TYPES: tuple[ActionType, ...] = (ActionType.DNS_WEIGHT_SHIFT, ActionType.TRAFFIC_REROUTE)

#: Expected seconds-to-recovery per action type, for the `latency` term.
#: Tier 1 config flips are fast by construction; later tiers (added here for
#: when candidates widen past Tier 1) recover slower.
STATIC_LATENCY_SECONDS: dict[ActionType, float] = {
    ActionType.DNS_WEIGHT_SHIFT: 20.0,
    ActionType.TRAFFIC_REROUTE: 30.0,
    ActionType.SCALE_OUT: 180.0,
    ActionType.REGION_FAILOVER: 300.0,
    ActionType.CROSS_CLOUD_FAILOVER: 420.0,
    ActionType.DR_PROMOTION: 900.0,
    ActionType.NO_OP: 0.0,
}
_DEFAULT_LATENCY_SECONDS = 60.0

#: Reversibility per tier, for the `safety` term -- ActionTier's own
#: docstring is the source: "Tier 1 is reversible in seconds. Tier 3 needs
#: human approval."
STATIC_SAFETY_PER_TIER: dict[ActionTier, float] = {
    ActionTier.TIER_1: 0.95,
    ActionTier.TIER_2: 0.60,
    ActionTier.TIER_3: 0.20,
}


class NoCandidateActions(RuntimeError):
    """Raised by `decide` if `CANDIDATE_TYPES` is ever emptied out from
    under it -- should never happen outside a test that does so on purpose."""


def candidate_actions(tenant_id: str, resource_id: str, incident_id: UUID) -> list[Action]:
    """Unsaved `Action`s -- nothing is persisted until one is chosen."""
    return [
        Action(
            incident_id=incident_id,
            tenant_id=tenant_id,
            provider=ProviderName.SIMULATED,
            type=action_type,
            tier=ActionTier.TIER_1,
            target_resource_id=resource_id,
            params={"source": "decision_engine"},
        )
        for action_type in CANDIDATE_TYPES
    ]


async def build_terms(
    action: Action, region: str, cap_usd: float, pricing: PricingSource
) -> dict[str, float]:
    """The four W5 terms for one candidate, each already normalised to
    [0, 1] as `validate_terms_and_weights` requires. Exposed (not
    underscored) because the monotonicity tests check this directly --
    "does a pricier candidate's `cost` term ever go down" is a question
    about term-building, not about which candidate `decide` ultimately picks.
    """
    estimate = await estimate_cost(action, region, pricing)
    cost_term = 1.0 if cap_usd <= 0 else min(1.0, estimate.projected_monthly_usd / cap_usd)
    latency_seconds = STATIC_LATENCY_SECONDS.get(action.type, _DEFAULT_LATENCY_SECONDS)
    latency_term = min(1.0, latency_seconds / 60.0)
    safety_term = STATIC_SAFETY_PER_TIER[action.tier]
    return {"ability": 1.0, "cost": cost_term, "latency": latency_term, "safety": safety_term}


async def decide(
    incident_id: UUID,
    tenant_id: str,
    resource_id: str,
    pricing: PricingSource,
) -> Decision:
    """Score every candidate, persist the winner's `Action` and the
    `Decision` itself (rejected candidates are kept as JSONB summaries on
    the `Decision`, not as rows in `actions` -- they were never going to
    run). Raises `NoCandidateActions` rather than return a meaningless
    Decision if there is nothing to choose from.
    """
    resource = get_resource_record(resource_id)
    region = str(resource["region"]) if resource else "sim-us-east-1"
    cap = get_monthly_budget_usd(tenant_id)

    actions = candidate_actions(tenant_id, resource_id, incident_id)
    if not actions:
        raise NoCandidateActions(f"no candidate actions for incident {incident_id}")

    scored: list[tuple[Action, dict[str, float], float]] = []
    for action in actions:
        terms = await build_terms(action, region, cap, pricing)
        scored.append((action, terms, score(terms, WEIGHTS)))

    scored.sort(key=lambda row: row[2], reverse=True)
    best_action, best_terms, best_utility = scored[0]
    rejected = [
        {
            "action_id": str(candidate.id),
            "action_type": candidate.type.value,
            "terms": terms,
            "utility": utility,
        }
        for candidate, terms, utility in scored[1:]
    ]

    decision = Decision(
        incident_id=incident_id,
        chosen_action=best_action,
        utility=best_utility,
        terms=best_terms,
        weights=WEIGHTS,
        formula_version=FORMULA_VERSION,
        rejected=rejected,
    )

    insert_action(best_action)
    insert_decision(decision, tenant_id)
    return decision
