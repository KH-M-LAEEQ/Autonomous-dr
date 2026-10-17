# Gate B practice summary (PB-13)

> **Practice result on simulator data, not the Gate B decision.** Every
> number below is quoted from `docs/results/results-v6.md`,
> `docs/results/results-v6-pyod.md`, `docs/results/breakdown-v6.md`,
> `docs/results/breakdown-v6-pyod.md`, and `docs/results/seed-sweep-v6.md` --
> nothing here is newly computed, and no harness was rerun to write it.

## 1. The question

Does Isolation Forest beat the threshold detector on F1 (the single number
Gate B will use to pick a winner)?

## 2. The answer on practice data: no

On `v6` (seed 42): `threshold` F1 0.833 (P 0.990, R 0.719, FPR 0.000) vs
`iforest` F1 0.625 (P 0.562, R 0.705, FPR 0.006).

Across all 5 practice seeds (42, 7, 123, 2024, 31337), `threshold` wins every
single one:

| Detector | Mean F1 | Min F1 | Max F1 |
| --- | --- | --- | --- |
| `threshold` | 0.825 | 0.787 | 0.842 |
| `iforest` | 0.618 | 0.589 | 0.634 |

No PyOD model beats `threshold` either (default hyperparameters, no tuning,
seed 42):

| Detector | F1 |
| --- | --- |
| `threshold` | 0.833 |
| `pyod_ecod` | 0.660 |
| `iforest` | 0.625 |
| `pyod_copod` | 0.608 |
| `pyod_hbos` | 0.510 |
| `pyod_lof` | 0.221 |
| `pyod_knn` | 0.156 |

(`pyod_ecod` is the only one of the five that edges past `iforest`; none
reach `threshold`.)

## 3. Why

**Fault-level detection is similar for both leading detectors** -- it's not
that `iforest` fails to find faults. Share of fault occurrences detected,
mean across the 5 seeds: `threshold` 0.873 (range 0.853-0.904), `iforest`
0.857 (range 0.813-0.908). That's a narrow gap.

**The gap is false alarms, mostly in the recovery phase** (the stretch right
after a fault clears, labelled normal in the official evaluation). On `v6`:
`threshold` has 7 false alarms total (5 normal, 2 recovery); `iforest` has
549 (38 normal, **511 recovery**). The PyOD family shows the same pattern for
3 of 5 models: `pyod_ecod` 350 total (11 normal, 339 recovery), `pyod_copod`
616 total (193 normal, 423 recovery), `pyod_hbos` 479 total (192 normal, 287
recovery). (`pyod_lof` and `pyod_knn` are more normal-phase-heavy: 1654/147
and 198/114 respectively -- not every model's false alarms concentrate in
recovery.)

**Post-hoc sensitivity analysis. Not the Gate B metric.** Recomputing F1 with
recovery-phase windows excluded from scoring narrows the gap a lot, but
`threshold` still wins: F1 (excl. recovery) `threshold` 0.834, `iforest`
0.809, `pyod_ecod` 0.794, `pyod_copod` 0.744, `pyod_hbos` 0.596, `pyod_lof`
0.232, `pyod_knn` 0.170. This view exists to show where the false alarms come
from, not to change which detector practice data favours.

## 4. Strengths per fault type

(Per-shape numbers below agree across `results-v6.md`'s shape table and
`breakdown-v6.md`'s per-fault-type table, section a -- both now keep
`cpu_hog` (sudden spike) and `intermittent` (burst) separate rows, so there
is no pooling to reconcile.)

- **Sudden spikes (`cpu_hog` shape) are a tie**: both detectors hit 1.000
  recall at the 40s hysteresis floor. No detector edge here on practice data.
- **Slow ramps (`gradual_ramp`) favour `iforest` on recall, `threshold` on
  speed**: `iforest` recall 1.000 vs `threshold`'s 0.800, but `iforest` is
  slower to call it (delay p50 240s, p95 448s, vs `threshold`'s p50 160s,
  p95 160s). Neither result is free: `iforest` trades speed for catching
  more of this shape.
- **Intermittent bursts favour `threshold` on recall, same speed**: recall
  0.840 vs `iforest`'s 0.680, both at the 40s delay floor. Separately, of the
  25 individual bursts in the test slice (`breakdown-v6.md` section c), every
  one sits exactly at the 3-consecutive-breach floor with no slack, and 23 of
  25 were caught by at least one of `threshold`/`iforest` -- the 2 missed by
  neither are a property of the 3-breach rule at that burst length, not a
  detector failure.
- **Small CPU steps (`small_step`) are missed by both**: 0.000 recall for
  `threshold` and `iforest` alike, and by every PyOD model except `pyod_lof`
  (which catches 1 of 5, slowly, at 200s delay). This fault shape sits below
  what most detectors tested here can separate from normal variation.

## 5. Caveats

- **Simulator-only data.** `SimulatedProvider` telemetry, not a real cloud or
  the Week 8 testbed -- faults here (`stop`/`pause`/`region_down` zero every
  signal) are often more extreme than real degradations.
- **`pyod_lof` and `pyod_knn` see unscaled features.** No per-signal scaling
  is applied anywhere before any detector's model sees a window vector (raw
  mean/std/last per signal, native units) -- tree-based (`iforest`) and
  distribution-based (`ecod`/`copod`/`hbos`) scorers don't need it, but the
  two distance-based models here do: a byte-rate signal in the millions can
  dominate a Euclidean distance over `cpu_percent`'s 0-100 range. Their low
  F1 in this practice run may understate what these models could do with
  scaled inputs; that comparison was out of scope here (default
  hyperparameters only, no tuning, no rescaling).
- **PyOD version as installed**: `pyod` 3.6.6, `pyproject.toml`'s `ml` extra
  currently pins only `pyod>=2.0`.
- **The PyOD feature-vectorizer is duplicated, not shared, code** --
  `ml/detectors/window_features.py` is a standalone copy of
  `ml/detectors/iforest.py`'s own vectorization logic (kept separate so
  `iforest.py`'s existing tests, which poke its private vectorizer
  attributes directly, didn't need to change). The duplication is
  test-guarded: `ml/tests/test_window_features.py` fits both on the same
  windows and asserts identical output, so a future edit to one that isn't
  mirrored in the other fails CI instead of silently drifting.

## 6. Status

This is a **practice result**, not the Gate B decision. The final Gate B run
uses the lockbox seed (9001) -- no dataset has been built from it and no
detector has been evaluated on it. It will be run exactly once, after which
no detector or setting may change.
