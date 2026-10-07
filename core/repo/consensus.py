"""Writes and reads against `proposals` and `votes`.

`proposals.action_id` has a FK to `actions.id` -- the action must already be
persisted (it is: `core.decision.engine.decide` inserts the chosen action
before returning it) before a proposal can reference it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from core.db import session_scope
from core.models.domain import Proposal, Vote
from core.models.enums import VoteChoice

_INSERT_PROPOSAL = text(
    """
    INSERT INTO proposals
        (id, tenant_id, incident_id, action_id, proposer_id, digest, created_at)
    VALUES
        (:id, :tenant_id, :incident_id, :action_id, :proposer_id, :digest, :created_at)
    """
)


def insert_proposal(proposal: Proposal, tenant_id: str) -> None:
    """`tenant_id` is not a `Proposal` field (ADR-0012's frozen shape) -- the
    caller supplies it, same convention as `core.repo.cost_estimates`."""
    with session_scope() as session:
        session.execute(
            _INSERT_PROPOSAL,
            {
                "id": str(proposal.id),
                "tenant_id": tenant_id,
                "incident_id": str(proposal.incident_id),
                "action_id": str(proposal.action.id),
                "proposer_id": proposal.proposer_id,
                "digest": proposal.digest,
                "created_at": proposal.created_at,
            },
        )


_MARK_COMMITTED = text(
    """
    UPDATE proposals SET
        committed = true, strategy = :strategy, latency_ms = :latency_ms,
        message_count = :message_count, note = :note
    WHERE id = :proposal_id
    """
)


def mark_proposal_committed(
    proposal_id: UUID, strategy: str, latency_ms: float, message_count: int, note: str | None = None
) -> None:
    with session_scope() as session:
        session.execute(
            _MARK_COMMITTED,
            {
                "proposal_id": str(proposal_id),
                "strategy": strategy,
                "latency_ms": latency_ms,
                "message_count": message_count,
                "note": note,
            },
        )


_GET_PROPOSAL = text("SELECT * FROM proposals WHERE id = :proposal_id")


def get_proposal_record(proposal_id: UUID | str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(_GET_PROPOSAL, {"proposal_id": str(proposal_id)}).first()
    return dict(row._mapping) if row is not None else None


_INSERT_VOTE = text(
    """
    INSERT INTO votes (id, tenant_id, proposal_id, voter_id, choice, reason, detection_id, cast_at)
    VALUES (gen_random_uuid(), :tenant_id, :proposal_id, :voter_id, :choice, :reason,
            :detection_id, :cast_at)
    """
)


def insert_vote(vote: Vote, tenant_id: str) -> None:
    with session_scope() as session:
        session.execute(
            _INSERT_VOTE,
            {
                "tenant_id": tenant_id,
                "proposal_id": str(vote.proposal_id),
                "voter_id": vote.voter_id,
                "choice": vote.choice.value,
                "reason": vote.reason,
                "detection_id": str(vote.detection_id) if vote.detection_id else None,
                "cast_at": vote.cast_at,
            },
        )


_GET_VOTES = text(
    "SELECT proposal_id, voter_id, choice, reason, detection_id, cast_at "
    "FROM votes WHERE proposal_id = :proposal_id ORDER BY cast_at ASC"
)


def get_votes_for_proposal(proposal_id: UUID | str) -> list[Vote]:
    with session_scope() as session:
        rows = session.execute(_GET_VOTES, {"proposal_id": str(proposal_id)}).all()
    return [
        Vote(
            proposal_id=row.proposal_id,
            voter_id=row.voter_id,
            choice=VoteChoice(row.choice),
            detection_id=row.detection_id,
            reason=row.reason,
            cast_at=row.cast_at,
        )
        for row in rows
    ]
