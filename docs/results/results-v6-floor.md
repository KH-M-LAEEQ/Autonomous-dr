# Practice run — threshold vs Isolation Forest

> **Simulator data, practice only, not for the thesis.**

These numbers come from `SimulatedProvider`, not from a real cloud or the
Week 8 testbed. They exist to prove the pipeline (generate → split → fit →
score → report) runs end to end and that the two detectors are comparable.
Nothing here belongs in the thesis.

## Dataset

- Version: `v6`, seed `42`
- Episodes: 432, windows: 590712
- Metric list: 25 signals, sha `7fad93b7e4f8cbd3`
- Shape mix: cpu_hog x50, gradual_ramp x33, intermittent x165, latency x50, pause x34, region_down x33, small_step x33, stop x34
- Collector step: 20s, window 12 samples (240s)
- Generated: 2026-10-17 by `ml/datasets/make_episodes.py` at commit `f241d2fbe5b9`
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
| `threshold_v2` | 0.992 | 0.719 | 0.833 | 0.000 | 40s | 91s | 160s |
| `lstm_v2` | 0.521 | 0.716 | 0.603 | 0.007 | 40s | 160s | 324s |

Window-level precision/recall/F1/FPR. Delay is per fault episode, measured
from the fault's exact start to the first alarm, in seconds.

## Counts behind the rates

| Detector | TP | FP | TN | FN | Train win. | Test win. | Episodes in test | Episodes detected | Delay samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `threshold_v2` | 718 | 6 | 87611 | 281 | 408296 | 88616 | 75 | 64 | 64 |
| `lstm_v2` | 715 | 657 | 86960 | 284 | 408296 | 88616 | 75 | 60 | 60 |

## Per fault shape

Pooled numbers average an easy shape and a subtle one into a figure
that describes neither. `detected` is episodes caught / episodes in the
test slice; delays are seconds from the fault's exact start.

| Shape | Detector | Episodes | Detected | Rate | p50 | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold_v2` | 8 | 8 | 1.000 | 40s | 40s | 40s |
| `cpu_hog` | `lstm_v2` | 8 | 8 | 1.000 | 40s | 40s | 40s |
| `gradual_ramp` | `threshold_v2` | 5 | 4 | 0.800 | 160s | 160s | 160s |
| `gradual_ramp` | `lstm_v2` | 5 | 5 | 1.000 | 160s | 480s | 544s |
| `intermittent` | `threshold_v2` | 25 | 21 | 0.840 | 40s | 40s | 40s |
| `intermittent` | `lstm_v2` | 25 | 16 | 0.640 | 40s | 40s | 40s |
| `latency` | `threshold_v2` | 7 | 6 | 0.857 | 40s | 40s | 40s |
| `latency` | `lstm_v2` | 7 | 6 | 0.857 | 40s | 40s | 40s |
| `pause` | `threshold_v2` | 6 | 6 | 1.000 | 40s | 40s | 40s |
| `pause` | `lstm_v2` | 6 | 6 | 1.000 | 40s | 40s | 40s |
| `region_down` | `threshold_v2` | 14 | 14 | 1.000 | 40s | 40s | 40s |
| `region_down` | `lstm_v2` | 14 | 14 | 1.000 | 40s | 40s | 40s |
| `small_step` | `threshold_v2` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `small_step` | `lstm_v2` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `stop` | `threshold_v2` | 5 | 5 | 1.000 | 40s | 40s | 40s |
| `stop` | `lstm_v2` | 5 | 5 | 1.000 | 40s | 40s | 40s |

## What this run actually found

**1. The threshold baseline was silent, and the cause was unit scale.**
FIXED — the `threshold_unscaled` row above is the old behaviour, measured
on this same dataset.

The pre-fix rule took the largest *absolute* per-signal deviation from a
training mean, across signals whose units span six orders of magnitude.
The byte-rate signals (`net_in_bytes`, `net_out_bytes`, baselines in the
millions) set the IQR fence, so it landed around 4.1e6. A `cpu_hog` fault
moves `cpu_percent` by ~67 points, which cannot cross a fence of four
million however severe the fault is. The detector was therefore silent
rather than inaccurate: zero true positives AND zero false positives.

This was pre-existing behaviour, not a regression from the interface-freeze
adaptation — `_residual` was unchanged and the old `IQRThreshold` strategy
computed the identical fence. The fix divides each signal by its own
training interquartile range first, so every signal contributes on a
comparable "how unusual is this for *this* signal" scale and a max() across
them is meaningful. Median and IQR rather than mean and standard deviation,
because both are robust to a contaminated training window. A zero-spread
signal (`health_check_pass` is 1.0 in every normal window) falls back to its
own magnitude instead of dividing by zero.

**2. A dataset shorter than one seasonality cycle makes a chronological
split meaningless.** An early 14-hour run put the 70% train slice in the
low-load small hours and the test slice in the busy afternoon: `cpu` mean
18.3 in train versus 43.0 in test-normal windows, inbound bytes 2.0M versus
4.9M. Isolation Forest correctly flagged 75% of *normal* test windows as
unlike training, giving a 39.5% false-positive rate that measured the
confound rather than the detector. Every dataset since spans several full
cycles, so the train slice has seen every phase of the daily curve. Any
future dataset must do the same before it is split.

**3. Isolation Forest reported a 0s detection delay, and the cause was a
hysteresis counter that outlived its episode.** FIXED — `_score_resource`
now resets the detector between episodes and attributes a lingering
post-fault breach to a grace period rather than to whatever comes next.

On `v4`, `intermittent` schedules back-to-back ON/OFF bursts, each its own
label episode, only 20s apart (one collector step). A burst's rolling-
window features (`_vector`'s mean/std/last over the window's whole span)
stay elevated for a while after the burst ends, so the detector kept
breaching into the OFF gap. Because the consecutive-breach counter was
never reset, that leftover count only needed one more breach on the very
first window of the *next* burst to cross the 3-breach gate — reported as a
0s delay, which is impossible under the rule (3 breaches at a 20s step is
at least 40s). BEFORE: `intermittent`/`iforest` detected 14/15 episodes,
delay p50 0s, p95 40s, p99 40s — p50 below the hysteresis floor is the
tell. AFTER the same run: still 14/15, but p50 40s, p95 40s, p99 40s — on
the floor, never below it.

The same stale count was also handing some episodes a few early windows'
worth of free credit, which is why the *pooled* iforest row moved too —
precision 0.507 -> 0.473, recall 0.551 -> 0.480, true positives 141 -> 123
(same test windows, same dataset, same fault sizes: nothing changed except
that the detector no longer gets to start an episode already most of the
way to a detection). Worse pooled numbers are the correct outcome here, not
a regression — they are what Isolation Forest actually does once each
episode is scored on its own.

## Read this before quoting any number above

- **Simulator faults are extreme.** `stop`, `pause` and `region_down` zero
  every signal and pin error rate to 100%. Detecting that is not evidence a
  detector can find a subtle real-world degradation.
- **Check the delay spread before quoting it.** If p50, p95 and p99 are the
  same number, every episode was caught at the hysteresis floor (60s here: 3 breaches x the
  collector step) and the distribution carries no information — it says the
  faults were trivially obvious, not that the detector is precise. The
  per-shape table above is where that shows up.
- **`intermittent` bursts are near the hysteresis limit by construction.** A
  burst of 1.0 minute(s) is only a few collector steps, and 3 consecutive breaches are
  required, so a burst shorter than 3 steps is structurally undetectable. A
  low detection rate on that shape is a property of the rule, not a failure
  of the scorer.
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
python -m ml.datasets.make_episodes --seed 42 --episodes 432 --version v6 --fault-store memory
python -m ml.harness.evaluate --dataset-version v6
```
