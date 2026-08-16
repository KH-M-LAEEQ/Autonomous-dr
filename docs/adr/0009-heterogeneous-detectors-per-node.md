# ADR-0009: Heterogeneous detectors per monitor node

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

The proposal claims that requiring three independent monitors to agree eliminates
false-positive-triggered recovery.

Three processes running the *same* detector over the *same* telemetry are not
independent. They will agree on every false positive, because a false positive is a
property of the detector, not of the process. Three identical verdicts arriving from
three PIDs is theatre, and a committee member will see through it in one question.

Note also that Liu et al. — cited in the proposal for this claim — say nothing about
monitors, anomaly detection or false positives. The paper is about consortium blockchain
throughput. The three-monitor design is ours; Liu is cited for PBFT mechanics only.

## Decision

Each monitor node runs a **different** detector, assigned by `NODE_DETECTOR`:

| Node | Detector | Deployment |
|---|---|---|
| node-a | Threshold | Quorum default & PBFT |
| node-b | Isolation Forest | Quorum default & PBFT |
| node-c | LSTM | Quorum default & PBFT |
| node-d | TBD at Week 24 (GNN suggested) | PBFT only (n=4 for f=1) |

All three poll the same telemetry. **Independence lives in the scoring method, not the
data source.** A statistical threshold, an unsupervised tree ensemble and a forecast
residual fail in different ways, so agreement between them is informative.

Each vote records the `detection_id` it came from, so a vote is traceable to the detector
that produced it.

## Consequences

**2-of-3 agreement means something.** A single detector's characteristic false positive
does not reach the action layer.

**Free results data.** Per-fault-type agreement rate across the three detectors is logged
from Week 17 (`docs/results/w17-detector-agreement.csv`) — a real table, at no extra cost.

**Week 17's "done when" gets teeth:** at least one logged case must show the three
detectors genuinely disagreeing.

**Latency is no longer uniform across nodes.** The threshold node returns in
milliseconds, the LSTM node does not. Week 28 breaks the latency distribution out per
detector rather than reporting a single mean.

**Node-d must be structurally distinct.** When PBFT stands up a fourth node in Week 24,
the GNN is the most different remaining option — it scores graph structure rather than
metric values.
