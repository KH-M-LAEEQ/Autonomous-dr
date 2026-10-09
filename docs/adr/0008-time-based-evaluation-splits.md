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

The evaluation harness splits chronologically — first 70% train, next 15%
validation, last 15% test — for every detector, every time.
`ml/harness/evaluate.py::time_based_split` owns the split, no caller
reimplements it, and `ml/tests/test_harness.py` asserts it never shuffles. The
validation slice exists so detectors that need a held-out set during fitting
(the W11 LSTM early-stops on it, patience=5) get one without picking their own
split: `AnomalyDetector.fit(X_train, X_val)` passes it in explicitly, and
`X_val` is `None` for detectors that don't use it (e.g. the threshold
baseline). Reported metrics — precision, recall, F1, false-positive rate,
detection delay in seconds — are computed on the test slice only; validation
is never scored.

## Consequences

**Good:** every detector that needs early stopping gets a val set from the
same place, so the Week 10 comparison table stays apples-to-apples instead of
each detector quietly picking its own holdout.

**Bad:** 15% less training data than the original 70/30 split, which matters
most for the data-hungry LSTM/GNN detectors (W11, W14).

## Alternatives considered

| Option | Why not |
| --- | --- |
| 70/30, let each detector carve its own val set out of train | breaks comparability — two detectors "trained on 70%" could see different data, and the harness can no longer attribute a metric difference to the model instead of the split |
| K-fold time-series cross-validation | more robust but 30+ weeks of one fixed split is what makes the results chapter's numbers comparable across every detector added later; add CV as an extra row per ADR-0008's original "revisit when," not as the primary split |

## Revisit when

Never for the chronological, never-shuffled, identical-across-detectors
invariant. Cross-validation variants may be added as extra rows; the primary
split does not change again after this amendment.

## Amendment (2026-09-12)

The 70/15/15 three-way split above supersedes this ADR's original 70/30
two-way split, to give detectors that require a held-out validation set
(early stopping) one without each inventing its own. The part of "revisit
when: never" that matters — chronological, never shuffled, identical across
every detector — is unchanged; only the slice count grew from two to three.
See ADR-0009 for the corresponding `AnomalyDetector.fit` signature change.
