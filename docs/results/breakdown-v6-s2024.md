# Per-fault-type and per-phase breakdown -- `v6-s2024`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6-s2024.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes.

| Fault type | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold` | 33 | 1.000 | 40s | 40s |
| `cpu_hog` | `iforest` | 33 | 1.000 | 40s | 40s |
| `cpu_ramp` | `threshold` | 5 | 0.800 | 150s | 177s |
| `cpu_ramp` | `iforest` | 5 | 1.000 | 220s | 416s |
| `cpu_step_small` | `threshold` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `iforest` | 5 | 0.000 | n/a | n/a |
| `latency` | `threshold` | 7 | 0.714 | 40s | 40s |
| `latency` | `iforest` | 7 | 0.714 | 40s | 40s |
| `pause` | `threshold` | 6 | 1.000 | 40s | 40s |
| `pause` | `iforest` | 6 | 1.000 | 40s | 40s |
| `region_down` | `threshold` | 14 | 1.000 | 40s | 40s |
| `region_down` | `iforest` | 14 | 1.000 | 40s | 40s |
| `stop` | `threshold` | 6 | 1.000 | 40s | 40s |
| `stop` | `iforest` | 6 | 1.000 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_step_small` | 5 |
| `latency` | 2 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold` | 4 (67%) | 0 (0%) | 2 (33%) | 0 (0%) | 6 |
| `iforest` | 48 (8%) | 0 (0%) | 560 (92%) | 0 (0%) | 608 |

- `threshold`: 6 false alarm(s) total -- 4 in `normal`, 2 in `recovery`.
- `iforest`: 608 false alarm(s) total -- 48 in `normal`, 560 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 368 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 369 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 370 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 371 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 372 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 373 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 374 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 375 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 376 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 377 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 390 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 391 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 392 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 393 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 394 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 405 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 406 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 407 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 408 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 409 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 423 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 424 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 425 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 426 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 427 | 60s | 3.0 | at_floor | `threshold`, `iforest` |

0 burst(s) below the floor (structurally uncatchable); 25 at the floor, of which 25 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold` | 76 | 68 | 0.895 |
| `iforest` | 76 | 69 | 0.908 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold` | 298 | 152 | 146 |
| `iforest` | 309 | 152 | 157 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | official | 0.992 | 0.716 | 0.831 | 0.000 |
| `threshold` | excl. recovery | 0.995 | 0.716 | 0.832 | 0.000 |
| `iforest` | official | 0.549 | 0.705 | 0.617 | 0.007 |
| `iforest` | excl. recovery | 0.939 | 0.705 | 0.805 | 0.001 |
