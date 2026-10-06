# Practice run — threshold vs Isolation Forest

> **Simulator data, practice only, not for the thesis.**

These numbers come from `SimulatedProvider`, not from a real cloud or the
Week 8 testbed. They exist to prove the pipeline (generate → split → fit →
score → report) runs end to end and that the two detectors are comparable.
Nothing here belongs in the thesis.

## Dataset

- Version: `v3`, seed `42`
- Episodes: 120, windows: 58608
- Metric list: 20 signals, sha `51ba8da8a0e71f98`
- Fault mix: cpu_hog x28, latency x23, pause x21, region_down x21, stop x27
- Generated: 2026-10-06 by `ml/datasets/make_episodes.py` at commit `f49167f38d51`
- Fault store: `memory`

Split is ADR-0008 70/15/15, chronological, never shuffled, applied
per resource. Training windows are normal-only; the test slice is the
last 15%.

## Results

| Detector | Precision | Recall | F1 | FPR | Delay p50 | Delay p95 | Delay p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `threshold` | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a |
| `iforest` | 0.277 | 0.678 | 0.393 | 0.024 | 120s | 120s | 120s |

Window-level precision/recall/F1/FPR. Delay is per fault episode, measured
from the fault's exact start to the first alarm, in seconds.

## Counts behind the rates

| Detector | TP | FP | TN | FN | Train win. | Test win. | Episodes in test | Episodes detected | Delay samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `threshold` | 0 | 0 | 8682 | 118 | 40331 | 8800 | 19 | 0 | 0 |
| `iforest` | 80 | 209 | 8473 | 38 | 40331 | 8800 | 19 | 19 | 19 |

## What this run actually found

Two things worth acting on, both more useful than the numbers themselves.

**1. The threshold baseline never fires at all.** Zero true positives and
zero false positives across the whole test slice — it is silent, not
inaccurate. The cause is that `ThresholdDetector._residual` takes the
largest *absolute* per-signal deviation from the training mean, across
signals whose units span six orders of magnitude. The byte-rate signals
(`network_*_bytes_per_s`, baseline in the millions) dominate it, so the
fitted IQR fence lands around 4.1e6. A `cpu_hog` fault moves `cpu_pct` by
~67 — which cannot cross a fence of four million no matter how severe the
fault is. Only a byte-rate collapse could, and not reliably.

This is pre-existing behaviour, not a regression from the interface-freeze
adaptation: `_residual` is unchanged, and the old `IQRThreshold` strategy
computed the identical fence. The fix is a normalisation decision (per-signal
z-score or min-max before taking the max deviation) and it changes the
project's permanent baseline detector, so it needs a decision rather than a
quiet patch.

**2. A dataset shorter than one seasonality cycle makes a chronological
split meaningless.** The first attempt used a 14-hour run. Because the
simulator's load follows a daily curve, the 70% train slice covered the
low-load small hours and the test slice the busy afternoon: `cpu_pct` mean
18.3 in train versus 43.0 in test-normal windows, `network_in` 2.0M versus
4.9M. Isolation Forest correctly flagged 75% of *normal* test windows as
unlike training, giving a 39.5% false-positive rate that measured the
confound, not the detector. Regenerating across 5.1 virtual days — so the
train slice spans ~3.6 full cycles and has seen every phase — dropped the
same detector's false-positive rate to the value in the table above.
Any future dataset must span several full cycles before it is split.

## Read this before quoting any number above

- **Simulator faults are extreme.** `stop`, `pause` and `region_down` zero
  every signal and pin error rate to 100%. Detecting that is not evidence a
  detector can find a subtle real-world degradation.
- **The delay distribution is degenerate here.** Every detected episode was
  caught at exactly the hysteresis floor (3 breaches x the collector step),
  so p50, p95 and p99 are the same number. That says the faults are trivially
  obvious, not that the detector is precise. p95/p99 are proof the metric is
  computed, not measurements of anything.
- **Both detectors share the same cutoff rule and the same 3-breach
  hysteresis** (Tukey IQR fence on training scores). That is deliberate, so
  the comparison isolates the scoring method. It also means neither is tuned.
- **No cross-validation, no hyperparameter search.** One seed, one split.
- **The collector step here is 60s, not
  production's 10s.** That was the trade-off for spanning several full
  seasonality cycles without a multi-gigabyte window file (see finding 2).
  It coarsens delay resolution to one step, which is why the floor is
  180s rather than 30s.
- **The 70/15/15 vs 70/30 split inconsistency** between ADR-0008 and
  `ml/harness/evaluate.py`'s own rule 1 is unresolved; this run used
  70/15/15. Resolving it changes the test-set size.
- **Generated telemetry has a seasonality curve but no multi-day drift,**
  and no provider-specific noise at all.

Regenerate with:

```
python -m ml.datasets.make_episodes --seed 42 --episodes 120 --version v3 --fault-store memory
python -m ml.harness.evaluate --dataset-version v3
```
