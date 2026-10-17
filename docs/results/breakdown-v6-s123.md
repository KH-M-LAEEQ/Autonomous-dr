# Per-fault-type and per-phase breakdown -- `v6-s123`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6-s123.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes.

| Fault type | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold` | 27 | 1.000 | 40s | 68s |
| `cpu_hog` | `iforest` | 27 | 1.000 | 40s | 40s |
| `cpu_ramp` | `threshold` | 5 | 0.200 | 80s | 80s |
| `cpu_ramp` | `iforest` | 5 | 0.200 | 160s | 160s |
| `cpu_step_small` | `threshold` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `iforest` | 5 | 0.200 | 80s | 80s |
| `latency` | `threshold` | 7 | 0.857 | 40s | 40s |
| `latency` | `iforest` | 7 | 0.857 | 40s | 40s |
| `pause` | `threshold` | 6 | 1.000 | 40s | 40s |
| `pause` | `iforest` | 6 | 1.000 | 40s | 40s |
| `region_down` | `threshold` | 14 | 1.000 | 40s | 40s |
| `region_down` | `iforest` | 14 | 1.000 | 40s | 40s |
| `stop` | `threshold` | 6 | 1.000 | 40s | 40s |
| `stop` | `iforest` | 6 | 1.000 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_ramp` | 4 |
| `cpu_step_small` | 4 |
| `latency` | 1 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold` | 2 (67%) | 0 (0%) | 1 (33%) | 0 (0%) | 3 |
| `iforest` | 85 (15%) | 0 (0%) | 497 (85%) | 0 (0%) | 582 |

- `threshold`: 3 false alarm(s) total -- 2 in `normal`, 1 in `recovery`.
- `iforest`: 582 false alarm(s) total -- 85 in `normal`, 497 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 379 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 380 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 381 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 382 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 383 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 394 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 395 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 396 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 397 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 398 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 399 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 400 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 401 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 402 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 403 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 427 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 428 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 429 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 430 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 431 | 60s | 3.0 | at_floor | `threshold`, `iforest` |

0 burst(s) below the floor (structurally uncatchable); 20 at the floor, of which 20 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold` | 70 | 60 | 0.857 |
| `iforest` | 70 | 61 | 0.871 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold` | 365 | 140 | 225 |
| `iforest` | 365 | 140 | 225 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | official | 0.996 | 0.650 | 0.787 | 0.000 |
| `threshold` | excl. recovery | 0.997 | 0.650 | 0.787 | 0.000 |
| `iforest` | official | 0.538 | 0.650 | 0.589 | 0.007 |
| `iforest` | excl. recovery | 0.889 | 0.650 | 0.751 | 0.001 |
