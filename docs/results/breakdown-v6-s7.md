# Per-fault-type and per-phase breakdown -- `v6-s7`

> **Diagnosis only, not for the thesis.** Regenerated from `ml/harness/evaluate.py --save-predictions` output; see `docs/results/results-v6-s7.md` for the headline numbers.

## a) Per fault type

`episodes`/`detected` are resource-occurrence counts, matching `results-v6.md`'s per-shape table convention -- an episode affecting multiple resources (`region_down`) is counted once per affected resource, so these totals reconcile with that table rather than with a plain count of distinct episodes.

| Fault type | Detector | Episodes | Recall | Delay p50 | Delay p95 |
| --- | --- | --- | --- | --- | --- |
| `cpu_hog` | `threshold` | 32 | 0.875 | 40s | 40s |
| `cpu_hog` | `iforest` | 32 | 0.781 | 40s | 40s |
| `cpu_ramp` | `threshold` | 4 | 1.000 | 150s | 160s |
| `cpu_ramp` | `iforest` | 4 | 1.000 | 180s | 200s |
| `cpu_step_small` | `threshold` | 5 | 0.000 | n/a | n/a |
| `cpu_step_small` | `iforest` | 5 | 0.000 | n/a | n/a |
| `latency` | `threshold` | 7 | 0.714 | 40s | 40s |
| `latency` | `iforest` | 7 | 0.714 | 40s | 40s |
| `pause` | `threshold` | 6 | 1.000 | 40s | 40s |
| `pause` | `iforest` | 6 | 1.000 | 40s | 40s |
| `region_down` | `threshold` | 16 | 1.000 | 40s | 40s |
| `region_down` | `iforest` | 16 | 1.000 | 40s | 40s |
| `stop` | `threshold` | 6 | 1.000 | 40s | 40s |
| `stop` | `iforest` | 6 | 1.000 | 40s | 40s |

Episodes missed by **both** detectors (deduplicated by episode id, unlike the table above):

| Fault type | Missed by both |
| --- | --- |
| `cpu_hog` | 3 |
| `cpu_step_small` | 5 |
| `latency` | 2 |

## b) False alarms by phase

`ramp`/`fault` cannot appear here by construction -- a false alarm is, by definition, a breach on a ground-truth-normal window, and those two phases only ever apply to a window already inside a labelled fault. Zero in those columns is the expected, structural answer, not a gap in the data.

| Detector | Normal | Ramp | Recovery | Other | Total |
| --- | --- | --- | --- | --- | --- |
| `threshold` | 2 (67%) | 0 (0%) | 1 (33%) | 0 (0%) | 3 |
| `iforest` | 72 (12%) | 0 (0%) | 524 (88%) | 0 (0%) | 596 |

- `threshold`: 3 false alarm(s) total -- 2 in `normal`, 1 in `recovery`.
- `iforest`: 596 false alarm(s) total -- 72 in `normal`, 524 in `recovery`.

## c) Intermittent bursts vs the hysteresis floor

`3` consecutive breaches are required to detect anything, so a burst shorter than that many collector steps is structurally undetectable regardless of score; a burst of exactly `3` steps has no slack at all -- every single step of it must breach, or the burst is missed.

| Episode | Burst length | Steps | vs floor | Caught by |
| --- | --- | --- | --- | --- |
| 379 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 380 | 60s | 3.0 | at_floor | `threshold` |
| 381 | 60s | 3.0 | at_floor | `threshold` |
| 382 | 60s | 3.0 | at_floor | `threshold` |
| 383 | 60s | 3.0 | at_floor | neither |
| 385 | 60s | 3.0 | at_floor | `threshold` |
| 386 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 387 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 388 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 389 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 402 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 403 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 404 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 405 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 406 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 409 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 410 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 411 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 412 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 413 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 425 | 60s | 3.0 | at_floor | neither |
| 426 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 427 | 60s | 3.0 | at_floor | `threshold`, `iforest` |
| 428 | 60s | 3.0 | at_floor | `iforest` |
| 429 | 60s | 3.0 | at_floor | neither |

0 burst(s) below the floor (structurally uncatchable); 25 at the floor, of which 22 were actually caught (zero tolerance for a missed step within the burst); 0 above the floor with at least one step of slack.

## d) Episode-level view

`occurrences`/`detected` are resource-occurrence counts (same convention as section a), summed across fault types.

| Detector | Fault occurrences | Detected | Share detected |
| --- | --- | --- | --- |
| `threshold` | 76 | 65 | 0.855 |
| `iforest` | 76 | 62 | 0.816 |

Of all missed (false-negative) windows, how many sit in the first `2` true-label windows of a fault at their resource -- unavoidable under the 3-consecutive-breach rule, since no alarm can fire before the counter reaches the gate -- versus a later window, which the detector had a real chance at:

| Detector | Missed windows | Unavoidable (first 2) | Later |
| --- | --- | --- | --- |
| `threshold` | 290 | 152 | 138 |
| `iforest` | 297 | 152 | 145 |

## e) Recovery-excluded sensitivity analysis

> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery windows are labelled normal in the official evaluation; this view excludes them to show where false alarms come from.

| Detector | View | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | official | 0.996 | 0.729 | 0.842 | 0.000 |
| `threshold` | excl. recovery | 0.997 | 0.729 | 0.842 | 0.000 |
| `iforest` | official | 0.564 | 0.722 | 0.634 | 0.007 |
| `iforest` | excl. recovery | 0.915 | 0.722 | 0.807 | 0.001 |
