# ADR-0004: Quorum first, PBFT as a pluggable strategy

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** core/interfaces/consensus_strategy.py, Weeks 5, 17, 24

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- 2-of-3 quorum is enough to stop a single rogue monitor, which is the actual threat model of the demo.
- PBFT is the ambitious contribution and the single largest schedule risk in the plan; it is cuttable at Gate C.
- Both must be measurable against each other for the results chapter.

## Decision

`ConsensusStrategy` is implemented twice against one unchanged signature:
`QuorumConsensus` (Week 5 single-node, Week 17 real 2-of-3) ships as the default,
`PBFTConsensus` (Week 24) is opt-in via `CONSENSUS=pbft`. Quorum stays the
default in every demo.

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

Never, for the default. If the Week 24 benchmark shows PBFT's latency is
acceptable at demo scale, that is a results-chapter finding, not a config change.
