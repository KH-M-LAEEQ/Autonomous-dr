# Practice run — threshold vs Isolation Forest

> **Simulator data, practice only, not for the thesis.**

These numbers come from `SimulatedProvider`, not from a real cloud or the
Week 8 testbed. They exist to prove the pipeline (generate → split → fit →
score → report) runs end to end and that the two detectors are comparable.
Nothing here belongs in the thesis.

## Dataset

- Version: `v4`, seed `42`
- Episodes: 150, windows: 177184
- Metric list: 25 signals, sha `7fad93b7e4f8cbd3`
- Fault mix: cpu_hog x81, cpu_ramp x8, cpu_step_small x10, latency x15, pause x18, region_down x11, stop x7
- Generated: 2026-10-06 by `ml/datasets/make_episodes.py` at commit `055935b6241b`
- Fault store: `memory`

Split is ADR-0008 70/15/15, chronological, never shuffled, applied
per resource. Training windows are normal-only; the test slice is the
last 15%.

## Results

`threshold_unscaled` is the BEFORE row: the baseline's pre-fix rule, run
by this same harness on this same dataset, so the comparison isolates the
per-signal scaling rather than quoting an old number from a different run.

| Detector | Precision | Recall | F1 | FPR | Delay p50 | Delay p95 | Delay p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `threshold_unscaled` | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a |
| `threshold` | 0.992 | 0.496 | 0.661 | 0.000 | 40s | 40s | 40s |
| `iforest` | 0.507 | 0.551 | 0.528 | 0.005 | 40s | 40s | 72s |

Window-level precision/recall/F1/FPR. Delay is per fault episode, measured
from the fault's exact start to the first alarm, in seconds.

## Counts behind the rates

| Detector | TP | FP | TN | FN | Train win. | Test win. | Episodes in test | Episodes detected | Delay samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `threshold_unscaled` | 0 | 0 | 26328 | 256 | 122433 | 26584 | 27 | 0 | 0 |
| `threshold` | 127 | 1 | 26327 | 129 | 122433 | 26584 | 27 | 22 | 22 |
| `iforest` | 141 | 137 | 26191 | 115 | 122433 | 26584 | 27 | 21 | 21 |

## Per fault shape

Pooled numbers average an easy shape and a subtle one into a figure
that describes neither. `detected` is episodes caught / episodes in the
test slice; delays are seconds from the fault's exact start.

| Shape | Detector | Episodes | Detected | Rate | p50 | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold_unscaled` | 1 | 0 | 0.000 | n/a | n/a | n/a |
| `cpu_hog` | `threshold` | 1 | 1 | 1.000 | 40s | 40s | 40s |
| `cpu_hog` | `iforest` | 1 | 1 | 1.000 | 80s | 80s | 80s |
| `intermittent` | `threshold_unscaled` | 15 | 0 | 0.000 | n/a | n/a | n/a |
| `intermittent` | `threshold` | 15 | 15 | 1.000 | 40s | 40s | 40s |
| `intermittent` | `iforest` | 15 | 14 | 0.933 | 0s | 40s | 40s |
| `latency` | `threshold_unscaled` | 2 | 0 | 0.000 | n/a | n/a | n/a |
| `latency` | `threshold` | 2 | 1 | 0.500 | 40s | 40s | 40s |
| `latency` | `iforest` | 2 | 1 | 0.500 | 40s | 40s | 40s |
| `pause` | `threshold_unscaled` | 1 | 0 | 0.000 | n/a | n/a | n/a |
| `pause` | `threshold` | 1 | 1 | 1.000 | 40s | 40s | 40s |
| `pause` | `iforest` | 1 | 1 | 1.000 | 40s | 40s | 40s |
| `region_down` | `threshold_unscaled` | 2 | 0 | 0.000 | n/a | n/a | n/a |
| `region_down` | `threshold` | 2 | 2 | 1.000 | 40s | 40s | 40s |
| `region_down` | `iforest` | 2 | 2 | 1.000 | 40s | 40s | 40s |
| `small_step` | `threshold_unscaled` | 4 | 0 | 0.000 | n/a | n/a | n/a |
| `small_step` | `threshold` | 4 | 0 | 0.000 | n/a | n/a | n/a |
| `small_step` | `iforest` | 4 | 0 | 0.000 | n/a | n/a | n/a |
| `stop` | `threshold_unscaled` | 2 | 0 | 0.000 | n/a | n/a | n/a |
| `stop` | `threshold` | 2 | 2 | 1.000 | 40s | 40s | 40s |
| `stop` | `iforest` | 2 | 2 | 1.000 | 40s | 40s | 40s |

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
- **The collector step here is 20s, not
  production's 10s.** That was the trade-off for spanning several full
  seasonality cycles without a multi-gigabyte window file (see finding 2).
  It coarsens delay resolution to one step, which is why the floor is
  60s rather than 30s.
- **The split is 70/15/15** (ADR-0008, `docs/formulas.md` section 2). The
  val slice is reserved for early stopping and has no consumer yet, so the
  test slice is the last 15% only.
- **Generated telemetry has a seasonality curve but no multi-day drift,**
  and no provider-specific noise at all.

Regenerate with:

```
python -m ml.datasets.make_episodes --seed 42 --episodes 150 --version v4 --fault-store memory
python -m ml.harness.evaluate --dataset-version v4
```
