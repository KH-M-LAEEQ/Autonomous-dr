# ADR-0008: Time-based evaluation splits

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

Our data is time series. A randomly shuffled train/test split puts future observations in
the training set and past observations in the test set, so the model is scored on
information it already saw. Reported F1 goes up and means nothing.

Every detector we build — threshold, Isolation Forest, LSTM, the ensemble, the PyOD
benchmark set, the GNN — has to be compared on identical splits, or the comparison table
that forms the core of the results chapter is not a comparison.

## Decision

Strictly temporal splits, never shuffled: **70% train / 15% validation / 15% test**,
following Karami et al. (arXiv:2510.11141), transcribed in `docs/formulas.md` §2.

The validation set exists so early stopping has somewhere to stop from. Normalisation
statistics (`μ`, `σ`) and IQR quartiles are computed on training data only.

The Week 10 evaluation harness implements this once, and every detector for the rest of
the project runs through it — including the Week 31 final run and the ablation study.

## Consequences

**Every number in the thesis is comparable.** One harness, one split rule, one metric set
defined in Week 10 and not touched again. A redefinition in March would invalidate
everything before it.

**Reported scores will be lower than a shuffled split would give.** They will also be
real.

**Smaller effective test set.** 15% of a continuously growing dataset is still large by
Week 31 (300+ labelled episodes), so this is not binding.

**Deviation from the original plan.** The plan said 70/30. That has no validation set and
therefore no basis for early stopping. 70/15/15 supersedes it.
