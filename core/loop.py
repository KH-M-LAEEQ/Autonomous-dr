"""`run_incident` -- Week 5's end-to-end orchestration.

One incident, once through the whole loop: decision -> cost gate ->
consensus -> executor. Each of those four steps gets its own `audit_log`
entry (the cost gate logs its own via `core.budget.check_budget`, which
this module calls rather than duplicates), and the incident's own state
machine (`core/incidents.py`) advances `open -> deciding -> acting ->
resolved | failed` as the loop proceeds -- never resolved without having
been through acting, never acting without a committed proposal.

Not re-entrant: this runs an incident through the loop exactly once. A
retried or re-opened incident is a later week's problem (idempotent re-runs
need to know which step it already got to, which nothing here tracks).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from core.budget import check_budget, estimate_cost
from core.decision.engine import decide
from core.incidents import get_incident, transition
from core.interfaces.action_executor import ActionExecutor
from core.interfaces.consensus_strategy import ConsensusStrategy
from core.interfaces.pricing_source import PricingSource
from core.logging import get_logger
from core.models.domain import Proposal
from core.models.enums import ActionStatus, IncidentState
from core.repo.actions import update_action_status
from core.repo.audit import append_entry
from core.repo.resources import get_resource_record

log = get_logger(__name__)


async def run_incident(
    incident_id: UUID,
    pricing: PricingSource,
    executor: ActionExecutor,
    consensus: ConsensusStrategy,
) -> IncidentState:
    """Returns the incident's final state (`RESOLVED` or `FAILED`)."""
    incident = get_incident(incident_id)
    if incident is None:
        raise KeyError(f"no incident {incident_id!r}")
    tenant_id = str(incident["tenant_id"])
    resource_id = str(incident["resource_id"])

    transition(incident_id, IncidentState.OPEN, IncidentState.DECIDING)

    # -- 1. decision ---------------------------------------------------
    decision = await decide(incident_id, tenant_id, resource_id, pricing)
    action = decision.chosen_action
    assert action is not None  # decide() always picks one of its candidates
    append_entry(
        actor="core.loop",
        action="incident.decision_made",
        payload={
            "incident_id": str(incident_id),
            "decision_id": str(decision.id),
            "action_id": str(action.id),
            "action_type": action.type.value,
            "utility": decision.utility,
        },
        tenant_id=tenant_id,
    )

    # -- 2. cost gate (logs its own audit_log entry) --------------------
    resource = get_resource_record(resource_id)
    region = str(resource["region"]) if resource else "sim-us-east-1"
    estimate = await estimate_cost(action, region, pricing)
    approved, reason = check_budget(estimate, tenant_id)
    if not approved:
        update_action_status(action.id, ActionStatus.REJECTED_BY_BUDGET, error=reason)
        transition(incident_id, IncidentState.DECIDING, IncidentState.FAILED)
        return IncidentState.FAILED
    update_action_status(action.id, ActionStatus.APPROVED)

    transition(incident_id, IncidentState.DECIDING, IncidentState.ACTING)

    # -- 3. consensus ----------------------------------------------------
    proposal = Proposal(
        incident_id=incident_id,
        action=action,
        proposer_id=consensus.node_id,
        created_at=datetime.now(UTC),
    )
    consensus_result = await consensus.propose(proposal)
    append_entry(
        actor="core.loop",
        action="incident.consensus_result",
        payload={
            "incident_id": str(incident_id),
            "proposal_id": str(proposal.id),
            "committed": consensus_result.committed,
            "strategy": consensus_result.strategy,
        },
        tenant_id=tenant_id,
    )
    if not consensus_result.committed:
        update_action_status(action.id, ActionStatus.REJECTED_BY_CONSENSUS)
        transition(incident_id, IncidentState.ACTING, IncidentState.FAILED)
        return IncidentState.FAILED

    # -- 4. executor -------------------------------------------------------
    update_action_status(action.id, ActionStatus.EXECUTING, started_at=datetime.now(UTC))
    try:
        exec_result = await executor.execute(action)
    except Exception as exc:
        update_action_status(
            action.id, ActionStatus.FAILED, error=str(exc), finished_at=datetime.now(UTC)
        )
        append_entry(
            actor="core.loop",
            action="incident.execution_failed",
            payload={
                "incident_id": str(incident_id),
                "action_id": str(action.id),
                "error": str(exc),
            },
            tenant_id=tenant_id,
        )
        transition(incident_id, IncidentState.ACTING, IncidentState.FAILED)
        return IncidentState.FAILED

    update_action_status(
        action.id,
        exec_result.status,
        provider_ref=exec_result.provider_ref,
        rollback_token=exec_result.rollback_token,
        finished_at=exec_result.finished_at or datetime.now(UTC),
    )
    append_entry(
        actor="core.loop",
        action="incident.action_executed",
        payload={
            "incident_id": str(incident_id),
            "action_id": str(action.id),
            "status": exec_result.status.value,
            "provider_ref": exec_result.provider_ref,
        },
        tenant_id=tenant_id,
    )

    transition(incident_id, IncidentState.ACTING, IncidentState.RESOLVED)
    return IncidentState.RESOLVED
