# Seed robustness check -- threshold vs Isolation Forest, `v6` schedule

> **Diagnosis only, not for the thesis.** Each row is a separate dataset built
> with the exact `v6` command from `docs/notes/gate-b-practice-v6.md`, with
> only `--seed` and `--version` changed (`v6` itself is seed `42`). No
> detector setting, the breach rule, the split, or the metrics changed between
> rows. `windows.jsonl` and `predictions-*.jsonl` were deleted after each
> dataset's results/breakdown were generated, to keep disk usage down; each
> dataset's `manifest.json` and `labels.jsonl` are kept so it can be
> regenerated bit-for-bit from the seed alone.

## Window-level metrics

| Seed | Detector | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| 42 | `threshold` | 0.990 | 0.719 | 0.833 | 0.000 |
| 42 | `iforest` | 0.562 | 0.705 | 0.625 | 0.006 |
| 7 | `threshold` | 0.996 | 0.729 | 0.842 | 0.000 |
| 7 | `iforest` | 0.564 | 0.722 | 0.634 | 0.007 |
| 123 | `threshold` | 0.996 | 0.650 | 0.787 | 0.000 |
| 123 | `iforest` | 0.538 | 0.650 | 0.589 | 0.007 |
| 2024 | `threshold` | 0.992 | 0.716 | 0.831 | 0.000 |
| 2024 | `iforest` | 0.549 | 0.705 | 0.617 | 0.007 |
| 31337 | `threshold` | 0.996 | 0.712 | 0.831 | 0.000 |
| 31337 | `iforest` | 0.565 | 0.697 | 0.624 | 0.006 |

| Detector | Stat | Precision | Recall | F1 | FPR |
| --- | --- | --- | --- | --- | --- |
| `threshold` | mean | 0.994 | 0.705 | 0.825 | 0.000 |
| `threshold` | min | 0.990 | 0.650 | 0.787 | 0.000 |
| `threshold` | max | 0.996 | 0.729 | 0.842 | 0.000 |
| `iforest` | mean | 0.556 | 0.696 | 0.618 | 0.007 |
| `iforest` | min | 0.538 | 0.650 | 0.589 | 0.006 |
| `iforest` | max | 0.565 | 0.722 | 0.634 | 0.007 |

## Episode-level detection (resource-occurrence counted)

| Seed | Detector | Detected | Total | Share detected |
| --- | --- | --- | --- | --- |
| 42 | `threshold` | 64 | 75 | 0.853 |
| 42 | `iforest` | 61 | 75 | 0.813 |
| 7 | `threshold` | 65 | 76 | 0.855 |
| 7 | `iforest` | 62 | 76 | 0.816 |
| 123 | `threshold` | 60 | 70 | 0.857 |
| 123 | `iforest` | 61 | 70 | 0.871 |
| 2024 | `threshold` | 68 | 76 | 0.895 |
| 2024 | `iforest` | 69 | 76 | 0.908 |
| 31337 | `threshold` | 66 | 73 | 0.904 |
| 31337 | `iforest` | 64 | 73 | 0.877 |

| Detector | Stat | Share detected |
| --- | --- | --- |
| `threshold` | mean | 0.873 |
| `threshold` | min | 0.853 |
| `threshold` | max | 0.904 |
| `iforest` | mean | 0.857 |
| `iforest` | min | 0.813 |
| `iforest` | max | 0.908 |

## Recovery-excluded F1 (post-hoc sensitivity, not the Gate B metric)

| Seed | Detector | F1 (official) | F1 (excl. recovery) |
| --- | --- | --- | --- |
| 42 | `threshold` | 0.833 | 0.834 |
| 42 | `iforest` | 0.625 | 0.809 |
| 7 | `threshold` | 0.842 | 0.842 |
| 7 | `iforest` | 0.634 | 0.807 |
| 123 | `threshold` | 0.787 | 0.787 |
| 123 | `iforest` | 0.589 | 0.751 |
| 2024 | `threshold` | 0.831 | 0.832 |
| 2024 | `iforest` | 0.617 | 0.805 |
| 31337 | `threshold` | 0.831 | 0.832 |
| 31337 | `iforest` | 0.624 | 0.802 |

| Detector | Stat | F1 (excl. recovery) |
| --- | --- | --- |
| `threshold` | mean | 0.825 |
| `threshold` | min | 0.787 |
| `threshold` | max | 0.842 |
| `iforest` | mean | 0.795 |
| `iforest` | min | 0.751 |
| `iforest` | max | 0.809 |

## Which detector had the higher official F1

- Seed 42: `threshold` (0.833 vs 0.625)
- Seed 7: `threshold` (0.842 vs 0.634)
- Seed 123: `threshold` (0.787 vs 0.589)
- Seed 2024: `threshold` (0.831 vs 0.617)
- Seed 31337: `threshold` (0.831 vs 0.624)

`threshold` wins on official window-level F1 for every seed tested, by a
comfortable margin each time (0.15-0.20 F1). Under the recovery-excluded
sensitivity view the gap narrows a lot (`iforest` closes to within ~0.02-0.04
F1 of `threshold`) because most of `iforest`'s false alarms land in the
recovery phase and nearly disappear once that phase is excluded -- see
`docs/results/breakdown-<version>.md` section b) per seed.

## Oddities

- **Seed 123 is the weakest dataset for both detectors** (window recall
  0.650/0.650, F1 0.787/0.589 -- the low end of the range for both), and also
  has noticeably more "later" (avoidable) missed windows than any other seed
  (225, vs 131-167 elsewhere) against a similar or smaller total episode
  count (70 vs 73-76). This is consistent with that seed's random draw
  happening to schedule a harder mix of fault instances, not a detector or
  harness change.
- `iforest`'s false-alarm phase split is recovery-dominated in every seed
  (85-93% of its false alarms land in `recovery`), and `threshold`'s handful
  of false alarms are almost entirely recovery too (`31337` is 100%
  recovery, 0 in `normal`) -- the pattern from the `v6` breakdown generalises
  across seeds, it is not a one-off.
- Detection delay percentiles (p50/p95/p99, not tabulated above -- see each
  seed's `results-<version>.md`) stay anchored at or near the 40s hysteresis
  floor for p50 in every seed for both detectors; only the tails (p95/p99)
  move with the seed.

Seed 9001 is reserved as a lockbox. No dataset is built from it and no
detector is evaluated on it until the final Gate B run, after which no
detector or setting may change.
