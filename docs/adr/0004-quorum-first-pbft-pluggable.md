# ADR-0004: Quorum first, PBFT as a pluggable strategy

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

The proposal commits to PBFT consensus preventing single-sensor false positives. PBFT is
also the single largest schedule risk in the plan: pre-prepare / prepare / commit phases,
view change on primary failure, checkpointing, and a Byzantine test suite. It is
scheduled for Week 24, behind everything else, and is cuttable at Gate C.

Building PBFT first would mean no working consensus until month six. Building only
simple quorum would mean not delivering what the proposal promised.

## Decision

A `ConsensusStrategy` interface — `propose(decision)`, `vote(proposal)`, `commit()` —
frozen in Week 2.

`QuorumConsensus` is the default: 3 nodes, 2-of-3 agreement, real from Week 17.
`PBFTConsensus` is opt-in by config, 4 nodes, delivered Week 24.

PBFT requires `n >= 3f + 1`, so tolerating one Byzantine node needs four, not three. The
constructor asserts `n == 3*f + 1` so a misconfigured deployment fails loudly instead of
silently claiming tolerance it does not have. Node counts and phase thresholds are in
`docs/formulas.md` §3.

## Consequences

**Working consensus in Week 17, not Week 24.** Gate C is reachable without PBFT existing.

**PBFT is cuttable without touching anything else.** It sits behind the interface. If
Gate C fails, it is the second item cut and nothing else changes.

**A real comparison instead of an assertion.** Week 24 benchmarks both strategies on the
same test suite — latency, message overhead, behaviour under a Byzantine node. PBFT will
be slower; explaining what that cost buys is a stronger result than shipping PBFT alone.

**Two deployment shapes.** Quorum at 3 nodes, PBFT at 4. The fourth node's detector is
decided in Week 24 (see ADR-0009).
