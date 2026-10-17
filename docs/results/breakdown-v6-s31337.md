# Per-fault-type and per-phase breakdown -- `v6-s31337`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6-s31337.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes.

| Fault type | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold` | 33 | 1.000 | 40s | 64s |
| `cpu_hog` | `iforest` | 33 | 0.939 | 40s | 40s |
| `cpu_ramp` | `threshold` | 5 | 0.800 | 150s | 180s |
| `cpu_ramp` | `iforest` | 5 | 0.800 | 230s | 328s |
| `cpu_step_small` | `threshold` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `iforest` | 5 | 0.000 | n/a | n/a |
| `latency` | `threshold` | 7 | 0.857 | 40s | 40s |
| `latency` | `iforest` | 7 | 0.857 | 40s | 40s |
| `pause` | `threshold` | 6 | 1.000 | 40s | 40s |
| `pause` | `iforest` | 6 | 1.000 | 40s | 40s |
| `region_down` | `threshold` | 12 | 1.000 | 40s | 40s |
| `region_down` | `iforest` | 12 | 1.000 | 40s | 40s |
| `stop` | `threshold` | 5 | 1.000 | 40s | 40s |
| `stop` | `iforest` | 5 | 1.000 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_ramp` | 1 |
| `cpu_step_small` | 5 |
| `latency` | 1 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold` | 0 (0%) | 0 (0%) | 3 (100%) | 0 (0%) | 3 |
| `iforest` | 43 (8%) | 0 (0%) | 512 (92%) | 0 (0%) | 555 |

- `threshold`: 3 false alarm(s) total -- 0 in `normal`, 3 in `recovery`.
- `iforest`: 555 false alarm(s) total -- 43 in `normal`, 512 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 378 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 379 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 380 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 381 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 382 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 385 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 386 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 387 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 388 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 389 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 401 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 402 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 403 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 404 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 405 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 407 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 408 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 409 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 410 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 411 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 427 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 428 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 429 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 430 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 431 | 60s | 3.0 | at_floor | `threshold`, `iforest` |

0 burst(s) below the floor (structurally uncatchable); 25 at the floor, of which 25 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold` | 73 | 66 | 0.904 |
| `iforest` | 73 | 64 | 0.877 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold` | 297 | 146 | 151 |
| `iforest` | 313 | 146 | 167 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | official | 0.996 | 0.712 | 0.831 | 0.000 |
| `threshold` | excl. recovery | 1.000 | 0.712 | 0.832 | 0.000 |
| `iforest` | official | 0.565 | 0.697 | 0.624 | 0.006 |
| `iforest` | excl. recovery | 0.944 | 0.697 | 0.802 | 0.001 |
