"""The evaluation harness -- Week 10, and the highest-leverage thing in the ml/ tree.

Rules that must never be broken, because every number in your thesis depends on them:
  1. Time-based split, 70/15/15 train/val/test. NEVER shuffle telemetry.
  2. Identical splits for every detector, every time.
  3. Report precision, recall, F1, false-positive rate, and detection delay in seconds.
  4. Bad results go in the table too.

Week 31 requires `make results` to regenerate every thesis figure from raw data
via this module. Design for that now; retrofitting it in March is miserable.

---

Implementation notes for the first working version:

**Labelling convention.** A window is anomalous iff its *most recent* sample
falls inside a fault interval (`fault_start <= window.end < fault_end`). That
mirrors how the live detector decides -- on the latest reading -- and it makes
detection delay well defined: the delay of an episode is
`first_alarm.window.end - fault_start`. Labelling by any-overlap instead would
mark a window anomalous when only its oldest sample is faulty, which flatters
recall and makes delay meaningless.

**One detector instance per resource.** Required by the `AnomalyDetector`
contract: the breach counter and the state behind `explain` are per-instance.
Each resource is also split, fitted and scored independently, then the counts
are pooled -- so a resource's detector never sees another resource's history.

**Training data is normal windows only.** Fault-overlapping windows are removed
from the train slice before `fit`. A novelty detector trained on a fault learns
that the fault is normal.

**Windows are streamed per resource.** `windows.jsonl` is hundreds of MB at
realistic episode counts; holding every window for every resource at once is
gigabytes of Python floats. One pass per resource keeps peak memory to a single
resource's history at the cost of re-reading the file, which is seconds.

**The split is 70/15/15, settled.** Rule 1 above used to say 70/30, which
contradicted ADR-0008 and `time_based_split`'s own defaults. `docs/formulas.md`
section 2 resolves it in favour of 70/15/15: the val slice is what early
stopping monitors (the W11 LSTM, patience 5), and "a 70/30 split has nowhere to
stop from". Code, docstring and ADR now agree. `_score_resource` filters the
val slice to fault-free windows the same way as train, then passes it as
`fit`'s `X_val` -- reserved for detectors that use it (the LSTM), a no-op for
the rest, and never folded into train or test.

**Episode boundaries reset detector hysteresis, and a fault's grace tail is
attributed to it, not stolen by whatever comes next.** `_score_resource` calls
`detector.reset()` (duck-typed, not part of the frozen `AnomalyDetector`
interface) at the first window strictly inside a new episode, and
`_grace_fault_at` lets a lingering breach just after a fault's labelled end
still count toward that fault rather than toward the next one. Both exist
because the Isolation Forest row of `docs/results/results-v5.md` reported a
0s detection delay on `intermittent`'s back-to-back bursts: a breach streak
from one burst's rolling-window tail only needed one more breach on the next
burst's very first window to "detect" it instantly. See that doc's
"zero-second detection delays" section for the full before/after.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any

from core.models.domain import MetricWindow
from ml.detectors import build

DEFAULT_DATASET_ROOT = Path("ml/datasets")


@dataclass(frozen=True)
class EvalResult:
    """One row of the results table. Keep the field names stable -- the thesis
    tables and the dashboard both read them."""

    detector: str
    dataset_version: str
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    detection_delay_p50_s: float
    detection_delay_p95_s: float
    detection_delay_p99_s: float
    n_episodes: int
    seed: int = 0
    notes: str = ""
    extra: dict[str, float] = field(default_factory=dict)
    #: Per fault-shape breakdown, keyed by `labels.jsonl`'s `shape`. Pooled
    #: numbers hide the thing worth knowing: an easy shape and a subtle one
    #: average into a figure that describes neither.
    by_shape: dict[str, dict[str, float]] = field(default_factory=dict)


def time_based_split(
    n: int, train_fraction: float = 0.7, val_fraction: float = 0.15
) -> tuple[slice, slice, slice]:
    """Chronological train/val/test split. The only splitting function allowed
    in this project (ADR-0008: 70/15/15, never shuffled, identical for every
    detector). `val` is what `AnomalyDetector.fit` receives as `X_val`; `test`
    is what gets scored.
    """
    train_cut = int(n * train_fraction)
    val_cut = train_cut + int(n * val_fraction)
    return slice(0, train_cut), slice(train_cut, val_cut), slice(val_cut, n)


def _percentile(data: list[float], q: float) -> float:
    """Linear-interpolation percentile, 0 <= q <= 100. Local copy on purpose:
    the harness must not import a detector's internals."""
    if not data:
        return float("nan")
    ordered = sorted(data)
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100) * (len(ordered) - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return ordered[int(rank)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


# -- dataset loading -------------------------------------------------------


@dataclass(frozen=True)
class FaultInterval:
    """Ground truth for one fault, as it applies to one resource."""

    episode: int
    fault_type: str
    start: datetime
    end: datetime
    #: How the fault was driven over time. Older datasets (v1-v3) predate
    #: shapes, so they fall back to the fault type.
    shape: str = "unknown"


def dataset_dir(dataset_version: str, root: Path = DEFAULT_DATASET_ROOT) -> Path:
    path = root / dataset_version
    if not (path / "manifest.json").exists():
        raise FileNotFoundError(
            f"no dataset at {path}. Generate one with "
            f"`python -m ml.datasets.make_episodes --version {dataset_version}`."
        )
    return path


def load_manifest(dataset_version: str, root: Path = DEFAULT_DATASET_ROOT) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(
        (dataset_dir(dataset_version, root) / "manifest.json").read_text()
    )
    return manifest


def load_fault_intervals(
    dataset_version: str, root: Path = DEFAULT_DATASET_ROOT
) -> dict[str, list[FaultInterval]]:
    """Fault intervals per resource id.

    A label's `affected` list is used, not just `target`: a `region_down` fault
    degrades every resource in the region, and scoring those as false positives
    would punish a detector for being right.
    """
    intervals: dict[str, list[FaultInterval]] = {}
    labels_path = dataset_dir(dataset_version, root) / "labels.jsonl"
    with labels_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            interval_args = {
                "episode": row["episode"],
                "fault_type": row["fault_type"],
                "start": datetime.fromisoformat(row["start"]),
                "end": datetime.fromisoformat(row["end"]),
                "shape": row.get("shape", row["fault_type"]),
            }
            for resource_id in row["affected"]:
                intervals.setdefault(resource_id, []).append(FaultInterval(**interval_args))
    return intervals


def _iter_windows(
    windows_path: Path, resource_id: str, *, use_prefilter: bool = True
) -> Iterator[MetricWindow]:
    """Windows for one resource, streamed.

    `use_prefilter` skips lines that cannot mention this resource with a
    substring test before paying for `json.loads`. At realistic dataset sizes
    the file is re-read once per resource per detector, so this is the
    difference between seconds and minutes. It is only ever an optimisation:
    the parsed row is still checked, and `load_windows_for_resource` re-runs
    the scan without it if the fast path finds nothing, so a future generator
    that formats JSON differently degrades in speed rather than silently
    returning an empty dataset.
    """
    needle = f'"resource_id": "{resource_id}"'
    with windows_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if use_prefilter and needle not in line:
                continue
            row = json.loads(line)
            if row["resource_id"] != resource_id:
                continue
            yield MetricWindow(
                resource_id=row["resource_id"],
                tenant_id=row["tenant_id"],
                start=datetime.fromisoformat(row["start"]),
                end=datetime.fromisoformat(row["end"]),
                step_seconds=row["step_seconds"],
                values=row["values"],
            )


def load_windows_for_resource(
    dataset_version: str, resource_id: str, root: Path = DEFAULT_DATASET_ROOT
) -> list[MetricWindow]:
    """Chronological windows for one resource. Sorted explicitly rather than
    trusting file order -- a future generator may interleave differently."""
    path = dataset_dir(dataset_version, root) / "windows.jsonl"
    windows = sorted(_iter_windows(path, resource_id), key=lambda w: w.end)
    if not windows:
        # Either the resource genuinely has no windows, or the substring fast
        # path missed because the file is formatted differently. Re-scan the
        # slow, always-correct way before believing the empty answer.
        windows = sorted(_iter_windows(path, resource_id, use_prefilter=False), key=lambda w: w.end)
    return windows


# -- scoring ---------------------------------------------------------------


def _fault_at(window: MetricWindow, intervals: list[FaultInterval]) -> FaultInterval | None:
    """The fault covering this window's most recent sample, if any."""
    for interval in intervals:
        if interval.start <= window.end < interval.end:
            return interval
    return None


def _grace_fault_at(
    window: MetricWindow, intervals: list[FaultInterval], grace: timedelta
) -> FaultInterval | None:
    """The most recently *ended* fault whose grace period still covers this
    window, if any. Only ever consulted once `_fault_at` has already returned
    `None` -- a window still strictly inside a (possibly different, later)
    fault always takes priority over an earlier fault's grace tail.

    Exists because a window's features are a rolling summary over its whole
    span (`_vector`'s mean/std/last), not a single instant: for up to one
    window-span after a fault clears, the window can still carry some
    fault-contaminated samples in its history and keep breaching the
    detector's cutoff. Without this, that lingering breach is attributed to
    whatever happens to be active when the 3rd consecutive breach lands --
    which, for `intermittent`'s back-to-back bursts, is usually the *next*
    episode, reported as a detection delay of 0s. See
    `docs/results/results-v5.md`, "zero-second detection delays".
    """
    if grace <= timedelta(0):
        return None
    candidates = [i for i in intervals if i.end <= window.end < i.end + grace]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i.end)


def _phase_of(
    fault: FaultInterval | None,
    window: MetricWindow,
    intervals: list[FaultInterval],
    recover: timedelta,
) -> str:
    """Which part of an episode's lifecycle this window sits in, for the
    opt-in prediction export only -- never consulted by the tally above.

    `fault` is `_fault_at(window, intervals)`, passed in rather than
    recomputed. `gradual_ramp` gets its own label because the whole point of
    that shape is a detector that only trips on extremes being LATE across
    it (see `_run_ramp` in `ml/datasets/make_episodes.py`); lumping it in
    with `fault` would hide that in the breakdown. `recovery` mirrors
    `_grace_fault_at`'s shape but uses the dataset's actual `recover_minutes`
    (from the manifest) rather than one window-span's grace -- a wider,
    label-only window with no effect on detection crediting.
    """
    if fault is not None:
        return "ramp" if fault.shape == "gradual_ramp" else "fault"
    if recover > timedelta(0) and any(i.end <= window.end < i.end + recover for i in intervals):
        return "recovery"
    return "normal"


@dataclass
class _Tally:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    train_windows: int = 0
    test_windows: int = 0
    delays_s: list[float] = field(default_factory=list)
    episodes_in_test: int = 0
    episodes_detected: int = 0
    delays_by_shape: dict[str, list[float]] = field(default_factory=dict)
    episodes_by_shape: dict[str, int] = field(default_factory=dict)
    detected_by_shape: dict[str, int] = field(default_factory=dict)


def _score_resource(
    detector_name: str,
    windows: list[MetricWindow],
    intervals: list[FaultInterval],
    tally: _Tally,
    detector_kwargs: dict[str, Any],
    predictions_out: IO[str] | None = None,
    recover: timedelta = timedelta(0),
) -> None:
    """Fit on this resource's normal train windows, score its test windows.

    **Episode boundaries reset the detector's hysteresis.** Right before the
    first window strictly inside a new episode's fault interval, `reset()` is
    called on the detector (if it has one -- a duck-typed extension, not part
    of the frozen `AnomalyDetector` interface). Without this, a breach streak
    that happened to be mid-count when episode N+1 begins -- whether from
    episode N's own grace tail or unrelated false-alarm noise in the gap --
    only needs one more breach to "detect" N+1 instantly, reporting a delay
    near 0s that measures carried-over state, not how fast the detector
    actually responded to this fault. See
    `docs/results/results-v5.md`, "zero-second detection delays".
    """
    if len(windows) < 10:
        return

    train_slice, val_slice, test_slice = time_based_split(len(windows))
    train_windows = [w for w in windows[train_slice] if _fault_at(w, intervals) is None]
    if len(train_windows) < 2:
        return

    val_windows = [w for w in windows[val_slice] if _fault_at(w, intervals) is None]

    detector = build(detector_name, **detector_kwargs)
    detector.fit(train_windows, val_windows or None)
    tally.train_windows += len(train_windows)

    first_alarm: dict[int, datetime] = {}
    episodes_seen: set[int] = set()
    active_episode: int | None = None
    # Grace period for attributing a lingering detection to the episode it
    # actually describes (see `_grace_fault_at`): one window's full span,
    # since that bounds how long fault-contaminated samples can still sit in
    # a window's rolling history after the fault itself has cleared.
    grace = windows[0].end - windows[0].start if windows else timedelta(0)

    test_windows = windows[test_slice]
    # Duck-typed batch scoring (like `reset()`): if the detector offers it,
    # score the whole test slice in one vectorised call instead of one call
    # per window -- see `IsolationForestDetector.score_batch`'s docstring
    # for why that is the dominant cost on a large dataset. `is_breach`
    # replays the exact same consecutive-breach/reset hysteresis `is_anomaly`
    # would have, just against an already-computed score.
    score_batch = getattr(detector, "score_batch", None)
    is_breach = getattr(detector, "is_breach", None)
    batch_scores: list[float] | None = None
    if callable(score_batch) and callable(is_breach):
        batch_scores = score_batch(test_windows)

    for index, window in enumerate(test_windows):
        tally.test_windows += 1
        fault = _fault_at(window, intervals)

        if fault is not None and fault.episode != active_episode:
            reset = getattr(detector, "reset", None)
            if callable(reset):
                reset()
            active_episode = fault.episode

        if batch_scores is not None and callable(is_breach):
            predicted = is_breach(batch_scores[index])
        else:
            predicted = detector.is_anomaly(window)

        if fault is not None:
            episodes_seen.add(fault.episode)
            if predicted:
                tally.tp += 1
            else:
                tally.fn += 1
        elif predicted:
            tally.fp += 1
        else:
            tally.tn += 1

        if predicted:
            # A detection before its episode's fault has even started is a
            # false alarm, not a catch -- `fault`/`_grace_fault_at` only ever
            # resolve to an interval at or after `interval.start`, so that
            # exclusion falls out of the lookup itself rather than needing a
            # separate check here.
            credited = fault if fault is not None else _grace_fault_at(window, intervals, grace)
            if (
                credited is not None
                and credited.episode in episodes_seen
                and credited.episode not in first_alarm
            ):
                first_alarm[credited.episode] = window.end

        if predictions_out is not None:
            # Export only -- read, never consulted by the tally above, so
            # turning it on cannot change a single number in `EvalResult`.
            score_value = (
                batch_scores[index] if batch_scores is not None else detector.score(window)
            )
            predictions_out.write(
                json.dumps(
                    {
                        "resource_id": window.resource_id,
                        "episode": fault.episode if fault is not None else None,
                        "fault_type": fault.fault_type if fault is not None else None,
                        "shape": fault.shape if fault is not None else None,
                        "phase": _phase_of(fault, window, intervals, recover),
                        "timestamp": window.end.isoformat(),
                        "true_label": fault is not None,
                        "breach": bool(predicted),
                        "score": float(score_value),
                    }
                )
                + "\n"
            )

    by_episode = {i.episode: i for i in intervals}
    tally.episodes_in_test += len(episodes_seen)
    tally.episodes_detected += len(first_alarm)
    for episode in episodes_seen:
        shape = by_episode[episode].shape
        tally.episodes_by_shape[shape] = tally.episodes_by_shape.get(shape, 0) + 1
    for episode, alarm_at in first_alarm.items():
        interval = by_episode[episode]
        delay = (alarm_at - interval.start).total_seconds()
        tally.delays_s.append(delay)
        tally.delays_by_shape.setdefault(interval.shape, []).append(delay)
        tally.detected_by_shape[interval.shape] = tally.detected_by_shape.get(interval.shape, 0) + 1


def evaluate(
    detector_name: str,
    dataset_version: str = "v1",
    root: Path = DEFAULT_DATASET_ROOT,
    save_predictions: bool = False,
    **detector_kwargs: Any,
) -> EvalResult:
    """Score one detector on one dataset version.

    Every resource is fitted and scored independently (one detector instance
    each, per the `AnomalyDetector` contract), then the window counts are pooled
    into a single set of metrics and the per-episode delays into one
    distribution.

    `save_predictions` is opt-in and off by default: when on, one row per
    TEST-slice window is appended to `<dataset>/predictions-<detector>.jsonl`
    (diagnosis only -- see `ml/harness/breakdown.py`). It is pure export: the
    tally loop in `_score_resource` never reads it back, so turning it on
    cannot change a single number in the returned `EvalResult`.
    """
    manifest = load_manifest(dataset_version, root)
    intervals_by_resource = load_fault_intervals(dataset_version, root)
    recover = timedelta(minutes=float(manifest.get("schedule", {}).get("recover_minutes", 0.0)))

    tally = _Tally()
    with ExitStack() as stack:
        predictions_out: IO[str] | None = None
        if save_predictions:
            predictions_path = (
                dataset_dir(dataset_version, root) / f"predictions-{detector_name}.jsonl"
            )
            predictions_out = stack.enter_context(
                predictions_path.open("w", encoding="utf-8", newline="\n")
            )

        for resource_id in manifest["resources"]:
            windows = load_windows_for_resource(dataset_version, resource_id, root)
            _score_resource(
                detector_name,
                windows,
                intervals_by_resource.get(resource_id, []),
                tally,
                detector_kwargs,
                predictions_out=predictions_out,
                recover=recover,
            )

    precision = tally.tp / (tally.tp + tally.fp) if (tally.tp + tally.fp) else 0.0
    recall = tally.tp / (tally.tp + tally.fn) if (tally.tp + tally.fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = tally.fp / (tally.fp + tally.tn) if (tally.fp + tally.tn) else 0.0

    return EvalResult(
        detector=detector_name,
        dataset_version=dataset_version,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=fpr,
        detection_delay_p50_s=_percentile(tally.delays_s, 50),
        detection_delay_p95_s=_percentile(tally.delays_s, 95),
        detection_delay_p99_s=_percentile(tally.delays_s, 99),
        n_episodes=tally.episodes_in_test,
        seed=int(manifest.get("seed", 0)),
        notes="simulator data, practice only, not for the thesis",
        extra={
            "true_positives": tally.tp,
            "false_positives": tally.fp,
            "true_negatives": tally.tn,
            "false_negatives": tally.fn,
            "train_windows": tally.train_windows,
            "test_windows": tally.test_windows,
            "episodes_detected": tally.episodes_detected,
            "episode_detection_rate": (
                tally.episodes_detected / tally.episodes_in_test if tally.episodes_in_test else 0.0
            ),
            "delay_samples": len(tally.delays_s),
        },
        by_shape={
            shape: {
                "episodes": float(count),
                "detected": float(tally.detected_by_shape.get(shape, 0)),
                "detection_rate": (tally.detected_by_shape.get(shape, 0) / count if count else 0.0),
                "delay_p50_s": _percentile(tally.delays_by_shape.get(shape, []), 50),
                "delay_p95_s": _percentile(tally.delays_by_shape.get(shape, []), 95),
                "delay_p99_s": _percentile(tally.delays_by_shape.get(shape, []), 99),
            }
            for shape, count in sorted(tally.episodes_by_shape.items())
        },
    )


# -- CLI -------------------------------------------------------------------

_BANNER = "> **Simulator data, practice only, not for the thesis.**"


def _fmt(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.3f}"


def _fmt_s(value: float) -> str:
    """Includes the unit, so a missing value reads `n/a` and not `n/as`."""
    return "n/a" if math.isnan(value) else f"{value:.0f}s"


def render_markdown(results: list[EvalResult], manifest: dict[str, Any]) -> str:
    lines = [
        "# Practice run — threshold vs Isolation Forest",
        "",
        _BANNER,
        "",
        "These numbers come from `SimulatedProvider`, not from a real cloud or the",
        "Week 8 testbed. They exist to prove the pipeline (generate → split → fit →",
        "score → report) runs end to end and that the two detectors are comparable.",
        "Nothing here belongs in the thesis.",
        "",
        "## Dataset",
        "",
        f"- Version: `{manifest['version']}`, seed `{manifest['seed']}`",
        f"- Episodes: {manifest['episode_count']}, windows: {manifest['window_count']}",
        f"- Metric list: {manifest['metric_list_version']['count']} signals, "
        f"sha `{manifest['metric_list_version']['sha256']}`",
        "- Shape mix: "
        + ", ".join(
            f"{k} x{v}"
            for k, v in (
                manifest.get("shape_distribution") or manifest["fault_type_distribution"]
            ).items()
        ),
        f"- Collector step: {manifest['virtual_clock']['step_seconds']}s, "
        f"window {manifest['window_samples']} samples "
        f"({manifest['virtual_clock']['step_seconds'] * manifest['window_samples']}s)",
        f"- Generated: {manifest['created']} by `{manifest['generator']}` "
        f"at commit `{manifest['generator_commit'][:12]}`",
        f"- Fault store: `{manifest['fault_store']}`",
        "",
        "Split is ADR-0008 70/15/15, chronological, never shuffled, applied",
        "per resource. Training windows are normal-only; the test slice is the",
        "last 15%.",
        "",
        "## Results",
        "",
        "`threshold_unscaled` is the BEFORE row: the baseline's pre-fix rule, run",
        "by this same harness on this same dataset, so the comparison isolates the",
        "per-signal scaling rather than quoting an old number from a different run.",
        "",
        "| Detector | Precision | Recall | F1 | FPR | Delay p50 | Delay p95 | Delay p99 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| `{r.detector}` | {_fmt(r.precision)} | {_fmt(r.recall)} | {_fmt(r.f1)} "
            f"| {_fmt(r.false_positive_rate)} | {_fmt_s(r.detection_delay_p50_s)} "
            f"| {_fmt_s(r.detection_delay_p95_s)} | {_fmt_s(r.detection_delay_p99_s)} |"
        )

    lines += [
        "",
        "Window-level precision/recall/F1/FPR. Delay is per fault episode, measured",
        "from the fault's exact start to the first alarm, in seconds.",
        "",
        "## Counts behind the rates",
        "",
        "| Detector | TP | FP | TN | FN | Train win. | Test win. | Episodes in test | "
        "Episodes detected | Delay samples |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        e = r.extra
        lines.append(
            f"| `{r.detector}` | {e['true_positives']:.0f} | {e['false_positives']:.0f} "
            f"| {e['true_negatives']:.0f} | {e['false_negatives']:.0f} "
            f"| {e['train_windows']:.0f} | {e['test_windows']:.0f} "
            f"| {r.n_episodes} | {e['episodes_detected']:.0f} | {e['delay_samples']:.0f} |"
        )

    shapes = sorted({s for r in results for s in r.by_shape})
    if shapes:
        lines += [
            "",
            "## Per fault shape",
            "",
            "Pooled numbers average an easy shape and a subtle one into a figure",
            "that describes neither. `detected` is episodes caught / episodes in the",
            "test slice; delays are seconds from the fault's exact start.",
            "",
            "| Shape | Detector | Episodes | Detected | Rate | p50 | p95 | p99 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for shape in shapes:
            for r in results:
                row = r.by_shape.get(shape)
                if not row:
                    continue
                lines.append(
                    f"| `{shape}` | `{r.detector}` | {row['episodes']:.0f} "
                    f"| {row['detected']:.0f} | {_fmt(row['detection_rate'])} "
                    f"| {_fmt_s(row['delay_p50_s'])} | {_fmt_s(row['delay_p95_s'])} "
                    f"| {_fmt_s(row['delay_p99_s'])} |"
                )

    lines += [
        "",
        "## What this run actually found",
        "",
        "**1. The threshold baseline was silent, and the cause was unit scale.**",
        "FIXED — the `threshold_unscaled` row above is the old behaviour, measured",
        "on this same dataset.",
        "",
        "The pre-fix rule took the largest *absolute* per-signal deviation from a",
        "training mean, across signals whose units span six orders of magnitude.",
        "The byte-rate signals (`net_in_bytes`, `net_out_bytes`, baselines in the",
        "millions) set the IQR fence, so it landed around 4.1e6. A `cpu_hog` fault",
        "moves `cpu_percent` by ~67 points, which cannot cross a fence of four",
        "million however severe the fault is. The detector was therefore silent",
        "rather than inaccurate: zero true positives AND zero false positives.",
        "",
        "This was pre-existing behaviour, not a regression from the interface-freeze",
        "adaptation — `_residual` was unchanged and the old `IQRThreshold` strategy",
        "computed the identical fence. The fix divides each signal by its own",
        "training interquartile range first, so every signal contributes on a",
        'comparable "how unusual is this for *this* signal" scale and a max() across',
        "them is meaningful. Median and IQR rather than mean and standard deviation,",
        "because both are robust to a contaminated training window. A zero-spread",
        "signal (`health_check_pass` is 1.0 in every normal window) falls back to its",
        "own magnitude instead of dividing by zero.",
        "",
        "**2. A dataset shorter than one seasonality cycle makes a chronological",
        "split meaningless.** An early 14-hour run put the 70% train slice in the",
        "low-load small hours and the test slice in the busy afternoon: `cpu` mean",
        "18.3 in train versus 43.0 in test-normal windows, inbound bytes 2.0M versus",
        "4.9M. Isolation Forest correctly flagged 75% of *normal* test windows as",
        "unlike training, giving a 39.5% false-positive rate that measured the",
        "confound rather than the detector. Every dataset since spans several full",
        "cycles, so the train slice has seen every phase of the daily curve. Any",
        "future dataset must do the same before it is split.",
        "",
        "**3. Isolation Forest reported a 0s detection delay, and the cause was a",
        "hysteresis counter that outlived its episode.** FIXED — `_score_resource`",
        "now resets the detector between episodes and attributes a lingering",
        "post-fault breach to a grace period rather than to whatever comes next.",
        "",
        "On `v4`, `intermittent` schedules back-to-back ON/OFF bursts, each its own",
        "label episode, only 20s apart (one collector step). A burst's rolling-",
        "window features (`_vector`'s mean/std/last over the window's whole span)",
        "stay elevated for a while after the burst ends, so the detector kept",
        "breaching into the OFF gap. Because the consecutive-breach counter was",
        "never reset, that leftover count only needed one more breach on the very",
        "first window of the *next* burst to cross the 3-breach gate — reported as a",
        "0s delay, which is impossible under the rule (3 breaches at a 20s step is",
        "at least 40s). BEFORE: `intermittent`/`iforest` detected 14/15 episodes,",
        "delay p50 0s, p95 40s, p99 40s — p50 below the hysteresis floor is the",
        "tell. AFTER the same run: still 14/15, but p50 40s, p95 40s, p99 40s — on",
        "the floor, never below it.",
        "",
        "The same stale count was also handing some episodes a few early windows'",
        "worth of free credit, which is why the *pooled* iforest row moved too —",
        "precision 0.507 -> 0.473, recall 0.551 -> 0.480, true positives 141 -> 123",
        "(same test windows, same dataset, same fault sizes: nothing changed except",
        "that the detector no longer gets to start an episode already most of the",
        "way to a detection). Worse pooled numbers are the correct outcome here, not",
        "a regression — they are what Isolation Forest actually does once each",
        "episode is scored on its own.",
        "",
        "## Read this before quoting any number above",
        "",
        "- **Simulator faults are extreme.** `stop`, `pause` and `region_down` zero",
        "  every signal and pin error rate to 100%. Detecting that is not evidence a",
        "  detector can find a subtle real-world degradation.",
        "- **Check the delay spread before quoting it.** If p50, p95 and p99 are the",
        f"  same number, every episode was caught at the hysteresis floor "
        f"({3 * manifest['virtual_clock']['step_seconds']}s here: 3 breaches x the",
        "  collector step) and the distribution carries no information — it says the",
        "  faults were trivially obvious, not that the detector is precise. The",
        "  per-shape table above is where that shows up.",
        "- **`intermittent` bursts are near the hysteresis limit by construction.** A",
        f"  burst of {manifest.get('shape_schedule', {}).get('intermittent_on_minutes', 1)} "
        f"minute(s) is only a few collector steps, and 3 consecutive breaches are",
        "  required, so a burst shorter than 3 steps is structurally undetectable. A",
        "  low detection rate on that shape is a property of the rule, not a failure",
        "  of the scorer.",
        "- **Both detectors share the same cutoff rule and the same 3-breach",
        "  hysteresis** (Tukey IQR fence on training scores). That is deliberate, so",
        "  the comparison isolates the scoring method. It also means neither is tuned.",
        "- **No cross-validation, no hyperparameter search.** One seed, one split.",
        f"- **The collector step here is {manifest['virtual_clock']['step_seconds']}s, not",
        "  production's 10s.** That was the trade-off for spanning several full",
        "  seasonality cycles without a multi-gigabyte window file (see finding 2).",
        "  It coarsens delay resolution to one step, which is why the floor is",
        f"  {3 * manifest['virtual_clock']['step_seconds']}s rather than 30s.",
        "- **The split is 70/15/15** (ADR-0008, `docs/formulas.md` section 2). The",
        "  val slice is reserved for early stopping and has no consumer yet, so the",
        "  test slice is the last 15% only.",
        "- **Generated telemetry has a seasonality curve but no multi-day drift,**",
        "  and no provider-specific noise at all.",
        "",
        "Regenerate with:",
        "",
        "```",
        f"python -m ml.datasets.make_episodes --seed {manifest['seed']} "
        f"--episodes {manifest['episode_count']} --version {manifest['version']} "
        f"--fault-store {manifest['fault_store']}",
        f"python -m ml.harness.evaluate --dataset-version {manifest['version']}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score detectors on a generated dataset.")
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument(
        "--detectors", nargs="+", default=["threshold_unscaled", "threshold", "iforest"]
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="defaults to docs/results/results-<dataset-version>.md",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--render-from",
        type=Path,
        default=None,
        help="re-render the markdown from a previous --json-out instead of "
        "re-scoring. Scoring reads the whole window file once per resource per "
        "detector, so this is the cheap path when only the prose changed.",
    )
    parser.add_argument(
        "--save-predictions",
        action="store_true",
        help="also write one row per TEST-slice window to "
        "<dataset-root>/<dataset-version>/predictions-<detector>.jsonl, for "
        "ml/harness/breakdown.py. Off by default; does not affect the metrics.",
    )
    args = parser.parse_args(argv)
    if args.out is None:
        args.out = Path(f"docs/results/results-{args.dataset_version}.md")

    manifest = load_manifest(args.dataset_version, args.dataset_root)
    results: list[EvalResult] = []
    if args.render_from:
        for row in json.loads(args.render_from.read_text()):
            results.append(EvalResult(**row))
        print(f"re-rendering {len(results)} result(s) from {args.render_from}")
    else:
        for name in args.detectors:
            print(f"scoring {name} on {args.dataset_version} ...", flush=True)
            result = evaluate(
                name,
                args.dataset_version,
                args.dataset_root,
                save_predictions=args.save_predictions,
            )
            results.append(result)
            print(
                f"  precision={result.precision:.3f} recall={result.recall:.3f} "
                f"f1={result.f1:.3f} fpr={result.false_positive_rate:.3f} "
                f"delay_p50={result.detection_delay_p50_s:.0f}s",
                flush=True,
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(results, manifest), encoding="utf-8", newline="\n")
    print(f"\nwrote {args.out}")

    if args.json_out and not args.render_from:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps([asdict(r) for r in results], indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
