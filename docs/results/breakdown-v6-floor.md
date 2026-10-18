# Per-fault-type and per-phase breakdown -- `v6`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes. Rows are split by `(fault_type, shape)`, not fault type alone -- `cpu_hog` covers both a sudden spike and an intermittent burst, which fail very differently under the hysteresis rule.

| Fault type | Shape | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `cpu_hog` | `threshold_v2` | 8 | 1.000 | 40s | 40s |
| `cpu_hog` | `cpu_hog` | `lstm_v2` | 8 | 1.000 | 40s | 40s |
| `cpu_hog` | `intermittent` | `threshold_v2` | 25 | 0.840 | 40s | 40s |
| `cpu_hog` | `intermittent` | `lstm_v2` | 25 | 0.640 | 40s | 40s |
| `cpu_ramp` | `gradual_ramp` | `threshold_v2` | 5 | 0.800 | 160s | 160s |
| `cpu_ramp` | `gradual_ramp` | `lstm_v2` | 5 | 1.000 | 160s | 480s |
| `cpu_step_small` | `small_step` | `threshold_v2` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `small_step` | `lstm_v2` | 5 | 0.000 | n/a | n/a |
| `latency` | `latency` | `threshold_v2` | 7 | 0.857 | 40s | 40s |
| `latency` | `latency` | `lstm_v2` | 7 | 0.857 | 40s | 40s |
| `pause` | `pause` | `threshold_v2` | 6 | 1.000 | 40s | 40s |
| `pause` | `pause` | `lstm_v2` | 6 | 1.000 | 40s | 40s |
| `region_down` | `region_down` | `threshold_v2` | 14 | 1.000 | 40s | 40s |
| `region_down` | `region_down` | `lstm_v2` | 14 | 1.000 | 40s | 40s |
| `stop` | `stop` | `threshold_v2` | 5 | 1.000 | 40s | 40s |
| `stop` | `stop` | `lstm_v2` | 5 | 1.000 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_hog` | 4 |
| `cpu_step_small` | 5 |
| `latency` | 1 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold_v2` | 4 (67%) | 0 (0%) | 2 (33%) | 0 (0%) | 6 |
| `lstm_v2` | 30 (5%) | 0 (0%) | 627 (95%) | 0 (0%) | 657 |

- `threshold_v2`: 6 false alarm(s) total -- 4 in `normal`, 2 in `recovery`.
- `lstm_v2`: 657 false alarm(s) total -- 30 in `normal`, 627 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 374 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 375 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 376 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 377 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 378 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 384 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 385 | 60s | 3.0 | at_floor | neither |
| 386 | 60s | 3.0 | at_floor | neither |
| 387 | 60s | 3.0 | at_floor | `threshold_v2` |
| 388 | 60s | 3.0 | at_floor | neither |
| 393 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 394 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 395 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 396 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 397 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 410 | 60s | 3.0 | at_floor | neither |
| 411 | 60s | 3.0 | at_floor | `threshold_v2` |
| 412 | 60s | 3.0 | at_floor | `threshold_v2` |
| 413 | 60s | 3.0 | at_floor | `threshold_v2` |
| 414 | 60s | 3.0 | at_floor | `threshold_v2` |
| 425 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 426 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 427 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 428 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |
| 429 | 60s | 3.0 | at_floor | `threshold_v2`, `lstm_v2` |

0 burst(s) below the floor (structurally uncatchable); 25 at the floor, of which 21 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold_v2` | 75 | 64 | 0.853 |
| `lstm_v2` | 75 | 60 | 0.800 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold_v2` | 281 | 150 | 131 |
| `lstm_v2` | 284 | 150 | 134 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold_v2` | official | 0.992 | 0.719 | 0.833 | 0.000 |
| `threshold_v2` | excl. recovery | 0.994 | 0.719 | 0.834 | 0.000 |
| `lstm_v2` | official | 0.521 | 0.716 | 0.603 | 0.007 |
| `lstm_v2` | excl. recovery | 0.960 | 0.716 | 0.820 | 0.000 |
