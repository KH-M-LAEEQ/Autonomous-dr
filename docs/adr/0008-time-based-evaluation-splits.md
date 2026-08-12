# ADR-0008: Time-based evaluation splits, never shuffled

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** ml/harness/evaluate.py, every number in the results chapter

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- Telemetry is autocorrelated and seasonal. A shuffled split leaks the future into the training set and inflates every metric.
- Eight or more detectors get compared across 30 weeks; the comparison is only meaningful if the split never changes.
- The one mistake that would invalidate the entire results chapter is the one to guard with a test.

## Decision

The evaluation harness splits chronologically — first 70% train, last 30% test —
for every detector, every time. `ml/harness/evaluate.py` owns the split, no
caller reimplements it, and `ml/tests/test_harness.py` asserts it never shuffles.
Reported metrics are precision, recall, F1, false-positive rate and detection
delay in seconds.

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

Never. Cross-validation variants may be added as extra rows; the primary split
does not change.
