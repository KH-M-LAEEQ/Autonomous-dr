# PyOD benchmark on v6 (PB-13)

> **Simulator data, practice only, not for the thesis.** Does not replace or
> overwrite `docs/results/results-v6.md` (threshold/iforest) -- see that file
> for the Gate B numbers.

Five PyOD models (`ecod`, `copod`, `hbos`, `lof`, `knn`), each wrapped by
`ml/detectors/pyod_detector.py` behind the same `AnomalyDetector` interface as
`iforest`: the same per-window feature vector (`WindowVectorizer`, a
verbatim copy of `iforest.py`'s vectorization -- see
`ml/detectors/window_features.py`), the same Tukey IQR fence over training
scores, and the same 3-consecutive-breach hysteresis. Every model is
constructed with PyOD's own default hyperparameters -- no tuning, per PB-13.
`iforest.py` itself was not touched to build this.

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

| Detector | Precision | Recall | F1 | FPR | Delay p50 | Delay p95 | Delay p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pyod_ecod` | 0.655 | 0.666 | 0.660 | 0.004 | 40s | 156s | 220s |
| `pyod_copod` | 0.534 | 0.707 | 0.608 | 0.007 | 40s | 120s | 207s |
| `pyod_hbos` | 0.514 | 0.507 | 0.510 | 0.005 | 40s | 61s | 180s |
| `pyod_lof` | 0.162 | 0.348 | 0.221 | 0.021 | 50s | 255s | 387s |
| `pyod_knn` | 0.262 | 0.111 | 0.156 | 0.004 | 40s | 410s | 578s |

Window-level precision/recall/F1/FPR. Delay is per fault episode, measured
from the fault's exact start to the first alarm, in seconds.

## Counts behind the rates

| Detector | TP | FP | TN | FN | Train win. | Test win. | Episodes in test | Episodes detected | Delay samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pyod_ecod` | 665 | 350 | 87267 | 334 | 408296 | 88616 | 75 | 52 | 52 |
| `pyod_copod` | 706 | 616 | 87001 | 293 | 408296 | 88616 | 75 | 54 | 54 |
| `pyod_hbos` | 506 | 479 | 87138 | 493 | 408296 | 88616 | 75 | 34 | 34 |
| `pyod_lof` | 348 | 1801 | 85816 | 651 | 408296 | 88616 | 75 | 34 | 34 |
| `pyod_knn` | 111 | 312 | 87305 | 888 | 408296 | 88616 | 75 | 15 | 15 |

## Per fault shape

Pooled numbers average an easy shape and a subtle one into a figure
that describes neither. `detected` is episodes caught / episodes in the
test slice; delays are seconds from the fault's exact start.

| Shape | Detector | Episodes | Detected | Rate | p50 | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `pyod_ecod` | 8 | 8 | 1.000 | 50s | 106s | 117s |
| `cpu_hog` | `pyod_copod` | 8 | 8 | 1.000 | 40s | 53s | 59s |
| `cpu_hog` | `pyod_hbos` | 8 | 1 | 0.125 | 40s | 40s | 40s |
| `cpu_hog` | `pyod_lof` | 8 | 3 | 0.375 | 180s | 216s | 219s |
| `cpu_hog` | `pyod_knn` | 8 | 0 | 0.000 | n/a | n/a | n/a |
| `gradual_ramp` | `pyod_ecod` | 5 | 3 | 0.600 | 200s | 236s | 239s |
| `gradual_ramp` | `pyod_copod` | 5 | 4 | 0.800 | 140s | 245s | 257s |
| `gradual_ramp` | `pyod_hbos` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `gradual_ramp` | `pyod_lof` | 5 | 1 | 0.200 | 420s | 420s | 420s |
| `gradual_ramp` | `pyod_knn` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `intermittent` | `pyod_ecod` | 25 | 10 | 0.400 | 40s | 40s | 40s |
| `intermittent` | `pyod_copod` | 25 | 11 | 0.440 | 40s | 40s | 40s |
| `intermittent` | `pyod_hbos` | 25 | 2 | 0.080 | 160s | 214s | 219s |
| `intermittent` | `pyod_lof` | 25 | 3 | 0.120 | 40s | 58s | 60s |
| `intermittent` | `pyod_knn` | 25 | 0 | 0.000 | n/a | n/a | n/a |
| `latency` | `pyod_ecod` | 7 | 6 | 0.857 | 40s | 40s | 40s |
| `latency` | `pyod_copod` | 7 | 6 | 0.857 | 40s | 40s | 40s |
| `latency` | `pyod_hbos` | 7 | 6 | 0.857 | 40s | 40s | 40s |
| `latency` | `pyod_lof` | 7 | 1 | 0.143 | 320s | 320s | 320s |
| `latency` | `pyod_knn` | 7 | 1 | 0.143 | 320s | 320s | 320s |
| `pause` | `pyod_ecod` | 6 | 6 | 1.000 | 40s | 40s | 40s |
| `pause` | `pyod_copod` | 6 | 6 | 1.000 | 40s | 40s | 40s |
| `pause` | `pyod_hbos` | 6 | 6 | 1.000 | 40s | 40s | 40s |
| `pause` | `pyod_lof` | 6 | 6 | 1.000 | 70s | 185s | 213s |
| `pause` | `pyod_knn` | 6 | 2 | 0.333 | 40s | 40s | 40s |
| `region_down` | `pyod_ecod` | 14 | 14 | 1.000 | 40s | 40s | 40s |
| `region_down` | `pyod_copod` | 14 | 14 | 1.000 | 40s | 40s | 40s |
| `region_down` | `pyod_hbos` | 14 | 14 | 1.000 | 40s | 40s | 40s |
| `region_down` | `pyod_lof` | 14 | 14 | 1.000 | 40s | 194s | 215s |
| `region_down` | `pyod_knn` | 14 | 11 | 0.786 | 40s | 330s | 562s |
| `small_step` | `pyod_ecod` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `small_step` | `pyod_copod` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `small_step` | `pyod_hbos` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `small_step` | `pyod_lof` | 5 | 1 | 0.200 | 200s | 200s | 200s |
| `small_step` | `pyod_knn` | 5 | 0 | 0.000 | n/a | n/a | n/a |
| `stop` | `pyod_ecod` | 5 | 5 | 1.000 | 40s | 40s | 40s |
| `stop` | `pyod_copod` | 5 | 5 | 1.000 | 40s | 40s | 40s |
| `stop` | `pyod_hbos` | 5 | 5 | 1.000 | 40s | 40s | 40s |
| `stop` | `pyod_lof` | 5 | 5 | 1.000 | 120s | 208s | 218s |
| `stop` | `pyod_knn` | 5 | 1 | 0.200 | 40s | 40s | 40s |

## Run times

Each detector run end-to-end (fit + score the full test slice +
`--save-predictions`), wall-clock, on this machine. None hit the 25-minute
cap.

| Detector | Elapsed | Status |
| --- | --- | --- |
| `pyod_ecod` | 477s (~8.0 min) | ok |
| `pyod_copod` | 434s (~7.2 min) | ok |
| `pyod_hbos` | 380s (~6.3 min) | ok |
| `pyod_lof` | 644s (~10.7 min) | ok |
| `pyod_knn` | 1278s (~21.3 min) | ok |

`knn` and `lof` are the slowest, as expected for nearest-neighbour methods
scored against a ~408k-window training set -- both are still well under the
25-minute cutoff, but the margin for `knn` is the thinnest of the five.

## What this run actually found

**None beats `threshold` on window-level F1; one (`ecod`) edges past `iforest`.**
Best of the five is `pyod_ecod` at F1 0.660 (P 0.655, R 0.666) -- above
`iforest`'s 0.625 but well below `threshold`'s 0.833. The other four trail
both (`copod` 0.608, `hbos` 0.510, `lof` 0.221, `knn` 0.156). See
`docs/results/results-v6.md` for the threshold/iforest numbers this compares
against -- not reproduced here to avoid two files disagreeing if one is
regenerated and the other isn't.

**`knn` and `lof` look weak mainly on recall, not precision.** Both have low
false-positive rates (`knn` FPR 0.004, `lof` FPR 0.021) but miss most fault
episodes outright: `knn` detects only 15/75 (0.200), `lof` 34/75 (0.453).
Per-shape, `knn` misses every `cpu_hog`, `gradual_ramp`, `intermittent`, and
`small_step` episode entirely (0/8, 0/5, 0/25, 0/5) -- its k-nearest-neighbour
distance score over mean/std/last features does not separate these shapes
from the training distribution well with PyOD's default `k=5`, untuned.

**`ecod` and `copod` (parameter-free, distribution-based) are the strongest
of the five**, both beating `hbos`/`lof`/`knn` on every metric except FPR,
where `ecod`'s 0.004 is the best in the family and `copod`'s 0.007 is
mid-pack. Neither model has a hyperparameter to tune by construction (PyOD's
own defaults are just `contamination`, unused here, same as `iforest`), so
this is not an artifact of favourable defaults the other three didn't get.

**`small_step` is undetected by every PyOD model, same as both existing
detectors** (0/5 for `ecod`, `copod`, `hbos`, `knn`; 1/5 for `lof`) -- this
fault shape is already known to be below the threshold/iforest detection
floor (`docs/results/breakdown-v6.md`), and nothing in this family changes
that.

## Read this before quoting any number above

- **Same caveats as `results-v6.md` apply**: simulator faults are extreme
  (`stop`/`pause`/`region_down` zero every signal), delay p50/p95/p99 being
  identical means every episode was caught at the 60s hysteresis floor and
  the distribution carries no information, `intermittent` bursts are near the
  hysteresis limit by construction, and there is no cross-validation or
  hyperparameter search -- one seed, one split, default parameters only.
- **These five share the IQR fence and 3-breach hysteresis with `iforest`,
  not with each other's PyOD defaults.** PyOD's own `contamination` cutoff is
  never consulted, by design -- the comparison isolates the scoring method,
  same rationale as `iforest.py`'s docstring.
- **`ecod`/`copod` recompute their score over train+batch jointly** (see
  `ml/detectors/pyod_detector.py`'s and `ml/tests/test_pyod_detector.py`'s
  `_BATCH_DEPENDENT` notes) -- the numbers above come from scoring the whole
  test slice in one `score_batch` call per resource, matching exactly how
  `ml/harness/evaluate.py` scores every detector; a window scored alone would
  not reproduce the same number for these two models.

Regenerate the tables above (Results/Counts/Per-fault-shape) with:

```
python -m ml.harness.evaluate --dataset-version v6 --detectors pyod_ecod pyod_copod pyod_hbos pyod_lof pyod_knn --save-predictions --out docs/results/results-v6-pyod.md
```

That command's own generated prose (banner, "What this run actually found",
caveats) is written for the threshold/iforest comparison and was replaced by
hand with the PyOD-specific analysis above -- rerunning it will restore the
generic prose, so re-edit this file's prose sections after regenerating.
