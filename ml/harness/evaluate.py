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
stop from". Code, docstring and ADR now agree. The val slice has no consumer
yet because the post-freeze `AnomalyDetector.fit` takes no `X_val`; it is
reserved, not spare, and must not be folded into train or test.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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


def dataset_dir(dataset_version: str, root: Path = DEFAULT_DATASET_ROOT) -> Path:
    path = root / dataset_version
    if not (path / "manifest.json").exists():
        raise FileNotFoundError(
            f"no dataset at {path}. Generate one with "
            f"`python -m ml.datasets.make_episodes --version {dataset_version}`."
        )
    return path


def load_manifest(dataset_version: str, root: Path = DEFAULT_DATASET_ROOT) -> dict[str, Any]:
    return json.loads((dataset_dir(dataset_version, root) / "manifest.json").read_text())


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
            }
            for resource_id in row["affected"]:
                intervals.setdefault(resource_id, []).append(FaultInterval(**interval_args))
    return intervals


def _iter_windows(windows_path: Path, resource_id: str) -> Iterator[MetricWindow]:
    with windows_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
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
    return sorted(_iter_windows(path, resource_id), key=lambda w: w.end)


# -- scoring ---------------------------------------------------------------


def _fault_at(window: MetricWindow, intervals: list[FaultInterval]) -> FaultInterval | None:
    """The fault covering this window's most recent sample, if any."""
    for interval in intervals:
        if interval.start <= window.end < interval.end:
            return interval
    return None


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


def _score_resource(
    detector_name: str,
    windows: list[MetricWindow],
    intervals: list[FaultInterval],
    tally: _Tally,
    detector_kwargs: dict[str, Any],
) -> None:
    """Fit on this resource's normal train windows, score its test windows."""
    if len(windows) < 10:
        return

    train_slice, _val_slice, test_slice = time_based_split(len(windows))
    train_windows = [w for w in windows[train_slice] if _fault_at(w, intervals) is None]
    if len(train_windows) < 2:
        return

    detector = build(detector_name, **detector_kwargs)
    detector.fit(train_windows)
    tally.train_windows += len(train_windows)

    first_alarm: dict[int, datetime] = {}
    episodes_seen: set[int] = set()

    for window in windows[test_slice]:
        tally.test_windows += 1
        fault = _fault_at(window, intervals)
        predicted = detector.is_anomaly(window)

        if fault is not None:
            episodes_seen.add(fault.episode)
            if predicted:
                tally.tp += 1
                if fault.episode not in first_alarm:
                    first_alarm[fault.episode] = window.end
            else:
                tally.fn += 1
        elif predicted:
            tally.fp += 1
        else:
            tally.tn += 1

    by_episode = {i.episode: i for i in intervals}
    tally.episodes_in_test += len(episodes_seen)
    tally.episodes_detected += len(first_alarm)
    for episode, alarm_at in first_alarm.items():
        tally.delays_s.append((alarm_at - by_episode[episode].start).total_seconds())


def evaluate(
    detector_name: str,
    dataset_version: str = "v1",
    root: Path = DEFAULT_DATASET_ROOT,
    **detector_kwargs: Any,
) -> EvalResult:
    """Score one detector on one dataset version.

    Every resource is fitted and scored independently (one detector instance
    each, per the `AnomalyDetector` contract), then the window counts are pooled
    into a single set of metrics and the per-episode delays into one
    distribution.
    """
    manifest = load_manifest(dataset_version, root)
    intervals_by_resource = load_fault_intervals(dataset_version, root)

    tally = _Tally()
    for resource_id in manifest["resources"]:
        windows = load_windows_for_resource(dataset_version, resource_id, root)
        _score_resource(
            detector_name,
            windows,
            intervals_by_resource.get(resource_id, []),
            tally,
            detector_kwargs,
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
        "- Fault mix: "
        + ", ".join(f"{k} x{v}" for k, v in manifest["fault_type_distribution"].items()),
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

    lines += [
        "",
        "## What this run actually found",
        "",
        "Two things worth acting on, both more useful than the numbers themselves.",
        "",
        "**1. The threshold baseline never fires at all.** Zero true positives and",
        "zero false positives across the whole test slice — it is silent, not",
        "inaccurate. The cause is that `ThresholdDetector._residual` takes the",
        "largest *absolute* per-signal deviation from the training mean, across",
        "signals whose units span six orders of magnitude. The byte-rate signals",
        "(`network_*_bytes_per_s`, baseline in the millions) dominate it, so the",
        "fitted IQR fence lands around 4.1e6. A `cpu_hog` fault moves `cpu_pct` by",
        "~67 — which cannot cross a fence of four million no matter how severe the",
        "fault is. Only a byte-rate collapse could, and not reliably.",
        "",
        "This is pre-existing behaviour, not a regression from the interface-freeze",
        "adaptation: `_residual` is unchanged, and the old `IQRThreshold` strategy",
        "computed the identical fence. The fix is a normalisation decision (per-signal",
        "z-score or min-max before taking the max deviation) and it changes the",
        "project's permanent baseline detector, so it needs a decision rather than a",
        "quiet patch.",
        "",
        "**2. A dataset shorter than one seasonality cycle makes a chronological",
        "split meaningless.** The first attempt used a 14-hour run. Because the",
        "simulator's load follows a daily curve, the 70% train slice covered the",
        "low-load small hours and the test slice the busy afternoon: `cpu_pct` mean",
        "18.3 in train versus 43.0 in test-normal windows, `network_in` 2.0M versus",
        "4.9M. Isolation Forest correctly flagged 75% of *normal* test windows as",
        "unlike training, giving a 39.5% false-positive rate that measured the",
        "confound, not the detector. Regenerating across 5.1 virtual days — so the",
        "train slice spans ~3.6 full cycles and has seen every phase — dropped the",
        "same detector's false-positive rate to the value in the table above.",
        "Any future dataset must span several full cycles before it is split.",
        "",
        "## Read this before quoting any number above",
        "",
        "- **Simulator faults are extreme.** `stop`, `pause` and `region_down` zero",
        "  every signal and pin error rate to 100%. Detecting that is not evidence a",
        "  detector can find a subtle real-world degradation.",
        "- **The delay distribution is degenerate here.** Every detected episode was",
        "  caught at exactly the hysteresis floor (3 breaches x the collector step),",
        "  so p50, p95 and p99 are the same number. That says the faults are trivially",
        "  obvious, not that the detector is precise. p95/p99 are proof the metric is",
        "  computed, not measurements of anything.",
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
    parser.add_argument("--detectors", nargs="+", default=["threshold", "iforest"])
    parser.add_argument("--out", type=Path, default=Path("docs/results/practice-run.md"))
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.dataset_version, args.dataset_root)
    results: list[EvalResult] = []
    for name in args.detectors:
        print(f"scoring {name} on {args.dataset_version} ...")
        result = evaluate(name, args.dataset_version, args.dataset_root)
        results.append(result)
        print(
            f"  precision={result.precision:.3f} recall={result.recall:.3f} "
            f"f1={result.f1:.3f} fpr={result.false_positive_rate:.3f} "
            f"delay_p50={result.detection_delay_p50_s:.0f}s"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(results, manifest), encoding="utf-8", newline="\n")
    print(f"\nwrote {args.out}")

    if args.json_out:
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
