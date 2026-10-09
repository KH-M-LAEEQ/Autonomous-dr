"""QuorumConsensus -- Week 5's `ConsensusStrategy`, single node.

Implements `core.interfaces.consensus_strategy.ConsensusStrategy`. With one
node, "quorum" is 1-of-1: this node's own vote is the whole protocol.
Week 17 widens it to a real 2-of-3 quorum across monitor nodes without
changing this class's shape -- only `propose`'s "am I the whole quorum"
logic needs to grow into "count real votes from real peers".

`fault_tolerance = 0`: a single node can't tolerate a single fault, Byzantine
or otherwise -- there is nobody to outvote it and nobody for it to outvote.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import UUID

from core.incidents import get_incident
from core.interfaces.consensus_strategy import ConsensusStrategy
from core.models.domain import ConsensusResult, Proposal, Vote
from core.models.enums import VoteChoice
from core.repo.consensus import (
    get_proposal_record,
    get_votes_for_proposal,
    insert_proposal,
    insert_vote,
    mark_proposal_committed,
)


class QuorumConsensus(ConsensusStrategy):
    name = "quorum"
    fault_tolerance = 0

    def __init__(self, node_id: str = "node-a") -> None:
        self.node_id = node_id

    async def vote(self, proposal: Proposal) -> Vote:
        """This node's own verdict -- re-derived from the incident this
        proposal is for, not trusted from the proposer, per the interface's
        contract (even though today, single-node, the proposer and the
        voter are the same process).

        `detection_id` comes from the incident's `trigger_detection_id`
        (ADR-0012): a `Proposal` carries no detection of its own, but a vote
        that cannot be traced to the detection that justified it is not
        explainable.
        """
        incident = get_incident(proposal.incident_id)
        detection_id = incident.get("trigger_detection_id") if incident else None
        return Vote(
            proposal_id=proposal.id,
            voter_id=self.node_id,
            choice=VoteChoice.APPROVE,
            detection_id=detection_id,
            reason="single-node quorum: no peer to disagree with yet",
            cast_at=datetime.now(UTC),
        )

    async def propose(self, proposal: Proposal) -> ConsensusResult:
        """Persists the proposal, casts this node's own vote, and commits
        immediately if that one vote is enough -- which, at 1-of-1, it
        always is unless this node rejects its own proposal."""
        start = time.monotonic()
        insert_proposal(proposal, proposal.action.tenant_id)

        my_vote = await self.vote(proposal)
        insert_vote(my_vote, proposal.action.tenant_id)

        committed = my_vote.choice == VoteChoice.APPROVE
        latency_ms = (time.monotonic() - start) * 1000.0
        if committed:
            mark_proposal_committed(
                proposal.id, self.name, latency_ms, message_count=1, note="1-of-1 quorum"
            )

        return ConsensusResult(
            proposal_id=proposal.id,
            committed=committed,
            votes=[my_vote],
            strategy=self.name,
            latency_ms=latency_ms,
            message_count=1,
            note=None if committed else "this node rejected its own proposal",
        )

    async def commit(self, proposal_id: str) -> ConsensusResult:
        """Idempotent: `propose` already commits a 1-of-1 quorum, so this is
        the re-read path -- re-committing an already-committed proposal is
        a no-op, not an error, per the interface's contract."""
        record = get_proposal_record(proposal_id)
        if record is None:
            raise KeyError(f"no proposal {proposal_id!r}")

        votes = get_votes_for_proposal(proposal_id)
        if not record["committed"]:
            mark_proposal_committed(
                UUID(str(proposal_id)),
                self.name,
                float(record["latency_ms"] or 0.0),
                message_count=len(votes),
                note="committed on re-read",
            )
            record["committed"] = True

        return ConsensusResult(
            proposal_id=UUID(str(proposal_id)),
            committed=bool(record["committed"]),
            votes=votes,
            strategy=self.name,
            latency_ms=float(record["latency_ms"] or 0.0),
            message_count=len(votes),
            note=record["note"],
        )
