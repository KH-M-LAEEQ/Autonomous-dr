# Gate B practice run — dataset v6

Date: 2026-10-17
Branch: `pr/j-dataset-v6` (based on `pr/i-influx-followups`)
Commit at build time: `f241d2fbe5b9a2c868cbf43477c0643719775f05`

## v5's full build command

v5's manifest schedule (65/180–600/10/20, not the generator's bare
defaults) could only have come from explicit flags beyond what
`docs/results/results-v5.md` documents. Reconstructed from every field
in `ml/datasets/v5/manifest.json` against `make_episodes.py --help`:

```
python -m ml.datasets.make_episodes \
  --seed 42 --episodes 300 --version v5 --fault-store memory \
  --normal-minutes 65 --fault-seconds-min 180 --fault-seconds-max 600 \
  --recover-minutes 10 --step-seconds 20 --ramp-minutes 10 \
  --small-step-seconds 300 --intermittent-on 1 --intermittent-off 1 \
  --intermittent-minutes 10 --window-samples 12 \
  --start 2026-01-01T00:00:00+00:00
python -m ml.harness.evaluate --dataset-version v6
```

v6 was rebuilt with the identical command (only `--version v6`).

## The 432 vs 648 episode mismatch, explained

`--episodes` sets `scheduled_episode_count` (generator loop iterations),
not `episode_count` (label rows, what the harness scores). An
`intermittent` episode emits one label row per ON burst (5 bursts/episode),
so `episode_count > scheduled_episode_count` whenever `intermittent` is in
the shape mix. v5's `episode_count` is 432 but its actual
`scheduled_episode_count` is **300** — the previous v6 attempt passed
`--episodes 432` (copying the wrong field from the manifest) and, combined
with un-matched schedule defaults, produced 648 label rows instead.

## Manifest diff (v5 vs rebuilt v6)

Only `version`, `simulator_version` (v6 has it, v5 predates the fix),
`created`, and `generator_commit` differ. `episode_count` (432),
`scheduled_episode_count` (300), `window_count` (590,712),
`shape_distribution`, `fault_type_distribution`, `virtual_clock`, and
`schedule` are byte-identical — **Step 2c passed**, so the "not
apples-to-apples" warning from the previous note is removed.

## v5 vs v6 results

| Detector | Dataset | Precision | Recall | F1 | FPR | p50 | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `threshold_unscaled` | v5 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a |
| `threshold_unscaled` | v6 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a |
| `threshold` | v5 | 1.000 | 0.719 | 0.836 | 0.000 | 40s | 100s | 145s |
| `threshold` | v6 | 0.990 | 0.719 | 0.833 | 0.000 | 40s | 91s | 160s |
| `iforest` | v5 | 0.554 | 0.688 | 0.613 | 0.006 | 40s | 144s | 288s |
| `iforest` | v6 | 0.562 | 0.705 | 0.625 | 0.006 | 40s | 200s | 344s |

p50 <= p95 <= p99 holds for both detectors on v6. No NaNs beyond the
expected `threshold_unscaled` baseline row. The small remaining deltas
(recall/F1 within ~1pt, delay tails shifted) come from simulator code
that changed between v5's generator commit (`b655650704fa...`) and v6's
(`f241d2fbe5b9...`) — notably the log-normal latency fix (`346fa62`) and
the strictly-positive-signal clamp removal (`5a2cd87`) — not from any
schedule or detector difference.

## Harness fix

`ml/harness/evaluate.py --out` now defaults to
`docs/results/results-<dataset-version>.md` instead of a fixed
`docs/results/practice-run.md`, so scoring one dataset version no longer
overwrites another's results file. v5's file was `git mv`'d to
`docs/results/results-v5.md` (content unchanged); this run wrote
`docs/results/results-v6.md`. Regression test:
`ml/tests/test_harness.py::test_main_writes_a_separate_results_file_per_dataset_version`.
Full suite (25 tests), ruff, and mypy all pass on the changed files.

No tests run beyond that, no detector settings changed, `core/interfaces/`
untouched.
