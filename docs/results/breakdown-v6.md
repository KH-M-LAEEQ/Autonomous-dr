# Per-fault-type and per-phase breakdown -- `v6`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes. Rows are split by `(fault_type, shape)`, not fault type alone -- `cpu_hog` covers both a sudden spike and an intermittent burst, which fail very differently under the hysteresis rule.

| Fault type | Shape | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `cpu_hog` | `threshold` | 8 | 1.000 | 40s | 40s |
| `cpu_hog` | `cpu_hog` | `iforest` | 8 | 1.000 | 40s | 40s |
| `cpu_hog` | `intermittent` | `threshold` | 25 | 0.840 | 40s | 40s |
| `cpu_hog` | `intermittent` | `iforest` | 25 | 0.680 | 40s | 40s |
| `cpu_ramp` | `gradual_ramp` | `threshold` | 5 | 0.800 | 160s | 160s |
| `cpu_ramp` | `gradual_ramp` | `iforest` | 5 | 1.000 | 240s | 448s |
| `cpu_step_small` | `small_step` | `threshold` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `small_step` | `iforest` | 5 | 0.000 | n/a | n/a |
| `latency` | `latency` | `threshold` | 7 | 0.857 | 40s | 40s |
| `latency` | `latency` | `iforest` | 7 | 0.857 | 40s | 40s |
| `pause` | `pause` | `threshold` | 6 | 1.000 | 40s | 40s |
| `pause` | `pause` | `iforest` | 6 | 1.000 | 40s | 40s |
| `region_down` | `region_down` | `threshold` | 14 | 1.000 | 40s | 40s |
| `region_down` | `region_down` | `iforest` | 14 | 1.000 | 40s | 40s |
| `stop` | `stop` | `threshold` | 5 | 1.000 | 40s | 40s |
| `stop` | `stop` | `iforest` | 5 | 1.000 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_hog` | 2 |
| `cpu_step_small` | 5 |
| `latency` | 1 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold` | 5 (71%) | 0 (0%) | 2 (29%) | 0 (0%) | 7 |
| `iforest` | 38 (7%) | 0 (0%) | 511 (93%) | 0 (0%) | 549 |

- `threshold`: 7 false alarm(s) total -- 5 in `normal`, 2 in `recovery`.
- `iforest`: 549 false alarm(s) total -- 38 in `normal`, 511 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 374 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 375 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 376 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 377 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 378 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 384 | 60s | 3.0 | at_floor | `threshold` |
| 385 | 60s | 3.0 | at_floor | `iforest` |
| 386 | 60s | 3.0 | at_floor | `iforest` |
| 387 | 60s | 3.0 | at_floor | `threshold` |
| 388 | 60s | 3.0 | at_floor | neither |
| 393 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 394 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 395 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 396 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 397 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 410 | 60s | 3.0 | at_floor | neither |
| 411 | 60s | 3.0 | at_floor | `threshold` |
| 412 | 60s | 3.0 | at_floor | `threshold` |
| 413 | 60s | 3.0 | at_floor | `threshold` |
| 414 | 60s | 3.0 | at_floor | `threshold` |
| 425 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 426 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 427 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 428 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 429 | 60s | 3.0 | at_floor | `threshold`, `iforest` |

0 burst(s) below the floor (structurally uncatchable); 25 at the floor, of which 23 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold` | 75 | 64 | 0.853 |
| `iforest` | 75 | 61 | 0.813 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold` | 281 | 150 | 131 |
| `iforest` | 295 | 150 | 145 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | official | 0.990 | 0.719 | 0.833 | 0.000 |
| `threshold` | excl. recovery | 0.993 | 0.719 | 0.834 | 0.000 |
| `iforest` | official | 0.562 | 0.705 | 0.625 | 0.006 |
| `iforest` | excl. recovery | 0.949 | 0.705 | 0.809 | 0.000 |
