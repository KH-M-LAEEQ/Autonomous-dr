# ADR-0012: Heterogeneous detectors per monitor node

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-24
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** core/config.py (`node_id`, `node_detector`), votes.detection_id, Weeks 17, 24, 28

## Context

The consensus layer exists to stop one faulty sensor from triggering a recovery
action. If all three monitor nodes run the same detector on the same telemetry,
they fail together: three processes return one opinion, and "2-of-3 agree" proves
nothing. That would be redundancy in name only.

## Decision

Each monitor node runs a **different** detector, chosen by `NODE_DETECTOR`:

| Node | Detector |
| --- | --- |
| node-a | Threshold |
| node-b | Isolation Forest |
| node-c | LSTM |
| node-d (PBFT only, Week 24) | decided in Week 24; GNN is the suggested option |

All nodes read the same telemetry. Independence is in the **scoring method**, not
the data source. Each vote records the `detection_id` it came from, so every vote
can be traced to the detector that produced it.

## Consequences

**Good:** a single rogue or mis-tuned detector cannot trigger an action alone. The
per-fault-type agreement rate across detectors is free data for the results chapter
(`docs/results/w17-detector-agreement.csv`). Disagreement is observable and logged.

**Bad:** the nodes have different latency (threshold is milliseconds, LSTM is not),
so quorum latency is set by the slowest voter; Week 28 reports this per detector.
Shared telemetry means a bad collector still fools all three, because independence
is only in the scoring.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Same detector on all three nodes | Not independent; consensus adds nothing |
| Different telemetry per node | Triples collector cost and breaks like-for-like comparison |

## Revisit when

If the Week 17 agreement data shows two detectors agreeing on almost every fault
type, their votes are close to redundant and the node mix should be reconsidered.
