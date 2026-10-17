# Per-fault-type and per-phase breakdown -- `v6`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes.

| Fault type | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold` | 33 | 0.879 | 40s | 40s |
| `cpu_hog` | `iforest` | 33 | 0.758 | 40s | 40s |
| `cpu_hog` | `pyod_ecod` | 33 | 0.545 | 40s | 86s |
| `cpu_hog` | `pyod_copod` | 33 | 0.576 | 40s | 42s |
| `cpu_hog` | `pyod_hbos` | 33 | 0.091 | 100s | 208s |
| `cpu_hog` | `pyod_lof` | 33 | 0.182 | 50s | 210s |
| `cpu_hog` | `pyod_knn` | 33 | 0.000 | n/a | n/a |
| `cpu_ramp` | `threshold` | 5 | 0.800 | 160s | 160s |
| `cpu_ramp` | `iforest` | 5 | 1.000 | 240s | 448s |
| `cpu_ramp` | `pyod_ecod` | 5 | 0.600 | 200s | 236s |
| `cpu_ramp` | `pyod_copod` | 5 | 0.800 | 140s | 245s |
| `cpu_ramp` | `pyod_hbos` | 5 | 0.000 | n/a | n/a |
| `cpu_ramp` | `pyod_lof` | 5 | 0.200 | 420s | 420s |
| `cpu_ramp` | `pyod_knn` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `threshold` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `iforest` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `pyod_ecod` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `pyod_copod` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `pyod_hbos` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `pyod_lof` | 5 | 0.200 | 200s | 200s |
| `cpu_step_small` | `pyod_knn` | 5 | 0.000 | n/a | n/a |
| `latency` | `threshold` | 7 | 0.857 | 40s | 40s |
| `latency` | `iforest` | 7 | 0.857 | 40s | 40s |
| `latency` | `pyod_ecod` | 7 | 0.857 | 40s | 40s |
| `latency` | `pyod_copod` | 7 | 0.857 | 40s | 40s |
| `latency` | `pyod_hbos` | 7 | 0.857 | 40s | 40s |
| `latency` | `pyod_lof` | 7 | 0.143 | 320s | 320s |
| `latency` | `pyod_knn` | 7 | 0.143 | 320s | 320s |
| `pause` | `threshold` | 6 | 1.000 | 40s | 40s |
| `pause` | `iforest` | 6 | 1.000 | 40s | 40s |
| `pause` | `pyod_ecod` | 6 | 1.000 | 40s | 40s |
| `pause` | `pyod_copod` | 6 | 1.000 | 40s | 40s |
| `pause` | `pyod_hbos` | 6 | 1.000 | 40s | 40s |
| `pause` | `pyod_lof` | 6 | 1.000 | 70s | 185s |
| `pause` | `pyod_knn` | 6 | 0.333 | 40s | 40s |
| `region_down` | `threshold` | 14 | 1.000 | 40s | 40s |
| `region_down` | `iforest` | 14 | 1.000 | 40s | 40s |
| `region_down` | `pyod_ecod` | 14 | 1.000 | 40s | 40s |
| `region_down` | `pyod_copod` | 14 | 1.000 | 40s | 40s |
| `region_down` | `pyod_hbos` | 14 | 1.000 | 40s | 40s |
| `region_down` | `pyod_lof` | 14 | 1.000 | 40s | 194s |
| `region_down` | `pyod_knn` | 14 | 0.786 | 40s | 330s |
| `stop` | `threshold` | 5 | 1.000 | 40s | 40s |
| `stop` | `iforest` | 5 | 1.000 | 40s | 40s |
| `stop` | `pyod_ecod` | 5 | 1.000 | 40s | 40s |
| `stop` | `pyod_copod` | 5 | 1.000 | 40s | 40s |
| `stop` | `pyod_hbos` | 5 | 1.000 | 40s | 40s |
| `stop` | `pyod_lof` | 5 | 1.000 | 120s | 208s |
| `stop` | `pyod_knn` | 5 | 0.200 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_hog` | 2 |
| `cpu_step_small` | 4 |
| `latency` | 1 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold` | 5 (71%) | 0 (0%) | 2 (29%) | 0 (0%) | 7 |
| `iforest` | 38 (7%) | 0 (0%) | 511 (93%) | 0 (0%) | 549 |
| `pyod_ecod` | 11 (3%) | 0 (0%) | 339 (97%) | 0 (0%) | 350 |
| `pyod_copod` | 193 (31%) | 0 (0%) | 423 (69%) | 0 (0%) | 616 |
| `pyod_hbos` | 192 (40%) | 0 (0%) | 287 (60%) | 0 (0%) | 479 |
| `pyod_lof` | 1654 (92%) | 0 (0%) | 147 (8%) | 0 (0%) | 1801 |
| `pyod_knn` | 198 (63%) | 0 (0%) | 114 (37%) | 0 (0%) | 312 |

- `threshold`: 7 false alarm(s) total -- 5 in `normal`, 2 in `recovery`.
- `iforest`: 549 false alarm(s) total -- 38 in `normal`, 511 in `recovery`.
- `pyod_ecod`: 350 false alarm(s) total -- 11 in `normal`, 339 in `recovery`.
- `pyod_copod`: 616 false alarm(s) total -- 193 in `normal`, 423 in `recovery`.
- `pyod_hbos`: 479 false alarm(s) total -- 192 in `normal`, 287 in `recovery`.
- `pyod_lof`: 1801 false alarm(s) total -- 1654 in `normal`, 147 in `recovery`.
- `pyod_knn`: 312 false alarm(s) total -- 198 in `normal`, 114 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 374 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 375 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 376 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 377 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod`, `pyod_lof` |
| 378 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 384 | 60s | 3.0 | at_floor | `threshold` |
| 385 | 60s | 3.0 | at_floor | `iforest`, `pyod_lof` |
| 386 | 60s | 3.0 | at_floor | `iforest` |
| 387 | 60s | 3.0 | at_floor | `threshold` |
| 388 | 60s | 3.0 | at_floor | neither |
| 393 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 394 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 395 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 396 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod` |
| 397 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_ecod`, `pyod_copod`, `pyod_hbos` |
| 410 | 60s | 3.0 | at_floor | neither |
| 411 | 60s | 3.0 | at_floor | `threshold` |
| 412 | 60s | 3.0 | at_floor | `threshold`, `pyod_hbos` |
| 413 | 60s | 3.0 | at_floor | `threshold`, `pyod_copod` |
| 414 | 60s | 3.0 | at_floor | `threshold` |
| 425 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 426 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 427 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 428 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 429 | 60s | 3.0 | at_floor | `threshold`, `iforest`, `pyod_lof` |

0 burst(s) below the floor (structurally uncatchable); 25 at the floor, of which 23 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold` | 75 | 64 | 0.853 |
| `iforest` | 75 | 61 | 0.813 |
| `pyod_ecod` | 75 | 52 | 0.693 |
| `pyod_copod` | 75 | 54 | 0.720 |
| `pyod_hbos` | 75 | 34 | 0.453 |
| `pyod_lof` | 75 | 34 | 0.453 |
| `pyod_knn` | 75 | 15 | 0.200 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold` | 281 | 150 | 131 |
| `iforest` | 295 | 150 | 145 |
| `pyod_ecod` | 334 | 150 | 184 |
| `pyod_copod` | 293 | 150 | 143 |
| `pyod_hbos` | 493 | 150 | 343 |
| `pyod_lof` | 651 | 150 | 501 |
| `pyod_knn` | 888 | 150 | 738 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | official | 0.990 | 0.719 | 0.833 | 0.000 |
| `threshold` | excl. recovery | 0.993 | 0.719 | 0.834 | 0.000 |
| `iforest` | official | 0.562 | 0.705 | 0.625 | 0.006 |
| `iforest` | excl. recovery | 0.949 | 0.705 | 0.809 | 0.000 |
| `pyod_ecod` | official | 0.655 | 0.666 | 0.660 | 0.004 |
| `pyod_ecod` | excl. recovery | 0.984 | 0.666 | 0.794 | 0.000 |
| `pyod_copod` | official | 0.534 | 0.707 | 0.608 | 0.007 |
| `pyod_copod` | excl. recovery | 0.785 | 0.707 | 0.744 | 0.002 |
| `pyod_hbos` | official | 0.514 | 0.507 | 0.510 | 0.005 |
| `pyod_hbos` | excl. recovery | 0.725 | 0.507 | 0.596 | 0.002 |
| `pyod_lof` | official | 0.162 | 0.348 | 0.221 | 0.021 |
| `pyod_lof` | excl. recovery | 0.174 | 0.348 | 0.232 | 0.019 |
| `pyod_knn` | official | 0.262 | 0.111 | 0.156 | 0.004 |
| `pyod_knn` | excl. recovery | 0.359 | 0.111 | 0.170 | 0.002 |
