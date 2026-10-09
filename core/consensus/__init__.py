"""ConsensusStrategy implementations. QuorumConsensus (W5 single-node, W17
real 2-of-3) and PBFTConsensus (W24) both live here."""

from core.consensus.quorum import QuorumConsensus

__all__ = ["QuorumConsensus"]
