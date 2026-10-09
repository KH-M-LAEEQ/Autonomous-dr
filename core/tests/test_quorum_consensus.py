"""Tests for core/consensus/quorum.py. Needs a real Postgres -- see
core/tests/conftest.py."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from core.db import ping

if not ping():
    pytest.skip(
        "Postgres is unreachable -- start it with `make up && make migrate`",
        allow_module_level=True,
    )

from core.consensus.quorum import QuorumConsensus
from core.incidents import open_incident
from core.models.domain import Action, Detection, Proposal
from core.models.enums import ActionTier, ActionType, ProviderName
from core.repo.actions import insert_action
from core.repo.detections import insert_detection
from core.tests.conftest import MakeDbTenant, resource_id_for

CONSENSUS = QuorumConsensus(node_id="node-a")


def _proposal_for(tenant_id: str, incident_id: UUID) -> Proposal:
    action = Action(
        incident_id=incident_id,
        tenant_id=tenant_id,
        provider=ProviderName.SIMULATED,
        type=ActionType.DNS_WEIGHT_SHIFT,
        tier=ActionTier.TIER_1,
        target_resource_id=resource_id_for(tenant_id),
    )
    insert_action(action)
    return Proposal(
        incident_id=incident_id,
        action=action,
        proposer_id="node-a",
        created_at=datetime.now(UTC),
    )


async def test_propose_commits_a_single_node_quorum(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant()
    incident_id = open_incident(tenant_id, resource_id_for(tenant_id))
    proposal = _proposal_for(tenant_id, incident_id)

    result = await CONSENSUS.propose(proposal)

    assert result.committed is True
    assert result.strategy == "quorum"
    assert len(result.votes) == 1
    assert result.votes[0].choice.value == "approve"
    assert result.message_count == 1
    assert result.latency_ms >= 0.0


async def test_vote_carries_the_incidents_trigger_detection_id(
    make_db_tenant: MakeDbTenant,
) -> None:
    tenant_id = make_db_tenant()
    resource_id = resource_id_for(tenant_id)
    detection = Detection(
        resource_id=resource_id,
        tenant_id=tenant_id,
        detector="threshold",
        score=0.9,
        is_anomaly=True,
        detected_at=datetime.now(UTC),
    )
    insert_detection(detection)
    incident_id = open_incident(tenant_id, resource_id, trigger_detection_id=detection.id)
    proposal = _proposal_for(tenant_id, incident_id)

    vote = await CONSENSUS.vote(proposal)

    assert vote.detection_id == detection.id


async def test_commit_is_idempotent(make_db_tenant: MakeDbTenant) -> None:
    tenant_id = make_db_tenant()
    incident_id = open_incident(tenant_id, resource_id_for(tenant_id))
    proposal = _proposal_for(tenant_id, incident_id)
    await CONSENSUS.propose(proposal)

    first = await CONSENSUS.commit(str(proposal.id))
    second = await CONSENSUS.commit(str(proposal.id))

    assert first.committed is True
    assert second.committed is True
    assert first.votes == second.votes


async def test_commit_of_an_unknown_proposal_raises() -> None:
    with pytest.raises(KeyError):
        await CONSENSUS.commit("00000000-0000-0000-0000-000000000000")
