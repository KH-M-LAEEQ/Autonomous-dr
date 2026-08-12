"""FROZEN INTERFACE 3 of 5 -- ConsensusStrategy.

Implemented by: QuorumConsensus (W5 single-node, W17 real 2-of-3) and
PBFTConsensus (W24, opt-in by config, cuttable at Gate C).

The reason PBFT is a schedule risk and not a schedule catastrophe is that it
lands behind this signature.
"""

from abc import ABC, abstractmethod

from core.models.domain import ConsensusResult, Proposal, Vote


class ConsensusStrategy(ABC):
    """Agreement among monitor nodes before any action executes.

    Contract:
      * No action is ever executed without a committed ConsensusResult.
      * A single rogue or lying node must not be able to commit a proposal.
      * A dead node must not be able to block a legitimate one.
      * `latency_ms` and `message_count` on the result are recorded for the
        Week 24 quorum-vs-PBFT benchmark -- populate them honestly.
    """

    name: str
    node_id: str
    fault_tolerance: int = 0  # f: Byzantine faults tolerated. Quorum = 0, PBFT = 1.

    @abstractmethod
    async def propose(self, proposal: Proposal) -> ConsensusResult:
        """Broadcast a proposal and run the protocol to completion or timeout."""
        ...

    @abstractmethod
    async def vote(self, proposal: Proposal) -> Vote:
        """This node's independent verdict. Must re-derive the decision from its
        own detections -- never trust the proposer's reasoning."""
        ...

    @abstractmethod
    async def commit(self, proposal_id: str) -> ConsensusResult:
        """Finalise and persist. Idempotent: committing twice is not an error."""
        ...
