"""Per-fault-type and per-phase breakdown for a dataset version -- diagnosis
only, not a thesis table.

Reads `ml/harness/evaluate.py`'s opt-in `--save-predictions` output
(`predictions-<detector>.jsonl`) plus `labels.jsonl`/`manifest.json` directly.
Every number here is downstream of the harness's own hysteresis-gated
`breach` decision -- this module never re-scores a window, changes the
breach rule, or touches the split. The one piece of harness logic it does
replay is first-alarm crediting (`_first_alarms_for_resource`, mirroring
`ml.harness.evaluate._score_resource`): the predictions file records a
window's ground-truth fault, not which episode a grace-period breach should
be credited to, so that step has to be redone here to get per-episode delay
and recall at all.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ml.detectors.threshold import CONSECUTIVE_BREACHES_REQUIRED
from ml.harness.evaluate import (
    DEFAULT_DATASET_ROOT,
    FaultInterval,
    _percentile,
    dataset_dir,
    load_fault_intervals,
    load_manifest,
)

DETECTORS: tuple[str, ...] = ("threshold", "iforest")
PHASES: tuple[str, ...] = ("normal", "ramp", "recovery", "other")


@dataclass(frozen=True)
class _Row:
    resource_id: str
    episode: int | None
    phase: str
    timestamp: datetime
    true_label: bool
    breach: bool


def _load_predictions(path: Path) -> list[_Row]:
    rows: list[_Row] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            rows.append(
                _Row(
                    resource_id=raw["resource_id"],
                    episode=raw["episode"],
                    phase=raw["phase"],
                    timestamp=datetime.fromisoformat(raw["timestamp"]),
                    true_label=raw["true_label"],
                    breach=raw["breach"],
                )
            )
    return rows


def _grace_interval_at(
    ts: datetime, intervals: list[FaultInterval], grace: timedelta
) -> FaultInterval | None:
    """Mirrors `ml.harness.evaluate._grace_fault_at`, against a bare
    timestamp instead of a `MetricWindow` -- the predictions file only ever
    carries `window.end`, not a full window."""
    if grace <= timedelta(0):
        return None
    candidates = [i for i in intervals if i.end <= ts < i.end + grace]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i.end)


def _first_alarms_for_resource(
    rows: list[_Row], intervals: list[FaultInterval], grace: timedelta
) -> tuple[set[int], dict[int, datetime]]:
    """Ground-truth episodes seen in this resource's test slice, and the
    timestamp each was first caught at -- replaying
    `ml.harness.evaluate._score_resource`'s crediting over an
    already-hysteresis-gated `breach` column, so a grace-period breach is
    attributed to the fault it tails rather than left uncredited."""
    episodes_seen = {r.episode for r in rows if r.true_label and r.episode is not None}
    first_alarm: dict[int, datetime] = {}
    for row in sorted(rows, key=lambda r: r.timestamp):
        if not row.breach:
            continue
        if row.true_label:
            credited_episode = row.episode
        else:
            grace_interval = _grace_interval_at(row.timestamp, intervals, grace)
            credited_episode = grace_interval.episode if grace_interval else None
        if credited_episode in episodes_seen and credited_episode not in first_alarm:
            first_alarm[credited_episode] = row.timestamp
    return episodes_seen, first_alarm


@dataclass
class _FaultTypeStats:
    """Resource-occurrence counted, matching `EvalResult.by_shape`'s existing
    convention (`docs/results/results-v6.md`): a `region_down` episode
    affecting 2 resources counts twice here, same as it does there. Kept
    deliberately consistent with the established numbers rather than
    deduplicated, so this table's totals reconcile with the main report's."""

    episodes: int = 0
    detected: int = 0
    delays_s: list[float] = field(default_factory=list)


def analyze_fault_types(
    predictions: dict[str, list[_Row]],
    intervals_by_resource: dict[str, list[FaultInterval]],
    episode_meta: dict[int, FaultInterval],
    grace: timedelta,
) -> tuple[dict[str, dict[str, _FaultTypeStats]], dict[str, set[int]], dict[str, set[int]]]:
    """Per (fault_type, detector) episode stats, plus -- deduplicated by
    episode id, unlike the table above -- which episodes each detector
    actually caught, so callers can ask "missed by both" without inheriting
    the resource-occurrence double counting."""
    stats: dict[str, dict[str, _FaultTypeStats]] = defaultdict(lambda: defaultdict(_FaultTypeStats))
    seen_ids: dict[str, set[int]] = defaultdict(set)
    detected_ids: dict[str, set[int]] = defaultdict(set)

    for detector, rows in predictions.items():
        by_resource: dict[str, list[_Row]] = defaultdict(list)
        for row in rows:
            by_resource[row.resource_id].append(row)

        for resource_id, resource_rows in by_resource.items():
            intervals = intervals_by_resource.get(resource_id, [])
            episodes_seen, first_alarm = _first_alarms_for_resource(resource_rows, intervals, grace)
            seen_ids[detector] |= episodes_seen
            detected_ids[detector] |= set(first_alarm)

            for episode in episodes_seen:
                meta = episode_meta[episode]
                row_stats = stats[meta.fault_type][detector]
                row_stats.episodes += 1
                if episode in first_alarm:
                    row_stats.detected += 1
                    row_stats.delays_s.append((first_alarm[episode] - meta.start).total_seconds())

    return stats, seen_ids, detected_ids


@dataclass
class _EpisodeLevelStats:
    """Totals across every fault type for one detector -- occurrence-counted,
    same convention as `_FaultTypeStats` (a `region_down` episode hitting 2
    resources counts twice), so these reconcile with the per-fault-type table
    and with `results-v6.md`'s `n_episodes`."""

    occurrences: int = 0
    detected: int = 0


def analyze_episode_level(
    fault_type_stats: dict[str, dict[str, _FaultTypeStats]],
    detectors: tuple[str, ...],
) -> dict[str, _EpisodeLevelStats]:
    """Collapses `analyze_fault_types`'s per-fault-type table across fault
    types, per detector -- the overall share of fault occurrences caught at
    all, independent of which fault type they were."""
    out: dict[str, _EpisodeLevelStats] = {}
    for detector in detectors:
        occurrences = sum(
            per_detector[detector].episodes
            for per_detector in fault_type_stats.values()
            if detector in per_detector
        )
        detected = sum(
            per_detector[detector].detected
            for per_detector in fault_type_stats.values()
            if detector in per_detector
        )
        out[detector] = _EpisodeLevelStats(occurrences, detected)
    return out


@dataclass
class _MissedWindowStats:
    """Missed (false-negative) windows split by whether an alarm was even
    possible yet. The first `CONSECUTIVE_BREACHES_REQUIRED - 1` true-label
    windows of a fault, at a given resource, cannot produce an alarm no
    matter how obviously anomalous they are -- the consecutive-breach counter
    has not reached the gate yet. Missing one of those is a property of the
    hysteresis rule, not of the detector; a miss on a later window is not."""

    unavoidable: int = 0
    later: int = 0


def missed_window_split(rows: list[_Row]) -> _MissedWindowStats:
    """Buckets one detector's missed windows by position within the fault at
    its resource (episode numbering is global across resources -- a
    `region_down` episode is one id shared by several resources, each with
    its own detector instance and its own hysteresis state -- so position is
    computed per (resource, episode), not per episode id alone)."""
    unavoidable_positions = CONSECUTIVE_BREACHES_REQUIRED - 1
    by_group: dict[tuple[str, int], list[_Row]] = defaultdict(list)
    for row in rows:
        if row.true_label and row.episode is not None:
            by_group[(row.resource_id, row.episode)].append(row)

    stats = _MissedWindowStats()
    for group_rows in by_group.values():
        for position, row in enumerate(sorted(group_rows, key=lambda r: r.timestamp)):
            if row.breach:
                continue
            if position < unavoidable_positions:
                stats.unavoidable += 1
            else:
                stats.later += 1
    return stats


@dataclass(frozen=True)
class _ConfusionCounts:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0


def _confusion(rows: list[_Row]) -> _ConfusionCounts:
    tp = fp = tn = fn = 0
    for row in rows:
        if row.true_label and row.breach:
            tp += 1
        elif row.true_label and not row.breach:
            fn += 1
        elif not row.true_label and row.breach:
            fp += 1
        else:
            tn += 1
    return _ConfusionCounts(tp, fp, tn, fn)


def _prf(c: _ConfusionCounts) -> tuple[float, float, float, float]:
    precision = c.tp / (c.tp + c.fp) if (c.tp + c.fp) else 0.0
    recall = c.tp / (c.tp + c.fn) if (c.tp + c.fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = c.fp / (c.fp + c.tn) if (c.fp + c.tn) else 0.0
    return precision, recall, f1, fpr


def recovery_excluded_sensitivity(
    predictions: dict[str, list[_Row]],
) -> dict[str, tuple[_ConfusionCounts, _ConfusionCounts]]:
    """Official window-level confusion counts vs the same counts with
    recovery-phase windows dropped from scoring entirely. Recovery windows
    are ground-truth normal in the official evaluation (the fault has
    already ended), so this only ever removes potential false positives --
    recall is unaffected by construction. Post-hoc, not the Gate B metric:
    see the label on this section in the rendered output."""
    out: dict[str, tuple[_ConfusionCounts, _ConfusionCounts]] = {}
    for detector, rows in predictions.items():
        official = _confusion(rows)
        excl_recovery = _confusion([r for r in rows if r.phase != "recovery"])
        out[detector] = (official, excl_recovery)
    return out


def false_alarms_by_phase(rows: list[_Row]) -> dict[str, int]:
    """False alarms (breach on a ground-truth-normal window) split by which
    part of the episode cycle they landed in. `ramp`/`fault` cannot appear
    here by construction -- `_phase_of` (`ml.harness.evaluate`) only assigns
    them when `true_label` is True, i.e. never on a false alarm -- so a
    non-zero `ramp` count here would mean the phase/true-label fields in the
    predictions file have gone out of sync, not that ramps cause false
    alarms."""
    counts: dict[str, int] = dict.fromkeys(PHASES, 0)
    for row in rows:
        if row.breach and not row.true_label:
            bucket = row.phase if row.phase in counts else "other"
            counts[bucket] += 1
    return counts


@dataclass(frozen=True)
class _BurstFloorRow:
    episode: int
    burst_seconds: float
    burst_steps: float
    bucket: str  # "below_floor" | "at_floor" | "above_floor"
    caught_by: tuple[str, ...]


def intermittent_floor_analysis(
    episode_meta: dict[int, FaultInterval],
    seen_episode_ids: set[int],
    detected_ids: dict[str, set[int]],
    step_seconds: float,
    detectors: tuple[str, ...],
) -> list[_BurstFloorRow]:
    """For every `intermittent` burst in the test slice: its length in
    collector steps against `CONSECUTIVE_BREACHES_REQUIRED` consecutive
    breaches, and which detectors (if any) caught it. A burst with fewer
    steps than the requirement cannot be caught under this rule no matter
    how obvious the fault is -- that is a property of the hysteresis, not of
    either detector."""
    rows: list[_BurstFloorRow] = []
    for episode in sorted(seen_episode_ids):
        meta = episode_meta[episode]
        if meta.shape != "intermittent":
            continue
        burst_seconds = (meta.end - meta.start).total_seconds()
        burst_steps = burst_seconds / step_seconds
        if burst_steps < CONSECUTIVE_BREACHES_REQUIRED:
            bucket = "below_floor"
        elif burst_steps == CONSECUTIVE_BREACHES_REQUIRED:
            bucket = "at_floor"
        else:
            bucket = "above_floor"
        caught_by = tuple(d for d in detectors if episode in detected_ids.get(d, set()))
        rows.append(_BurstFloorRow(episode, burst_seconds, burst_steps, bucket, caught_by))
    return rows


def _episode_meta(
    intervals_by_resource: dict[str, list[FaultInterval]],
) -> dict[int, FaultInterval]:
    meta: dict[int, FaultInterval] = {}
    for intervals in intervals_by_resource.values():
        for interval in intervals:
            meta[interval.episode] = interval
    return meta


def _fmt(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.3f}"


def _fmt_s(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.0f}s"


def render_markdown(
    dataset_version: str,
    fault_type_stats: dict[str, dict[str, _FaultTypeStats]],
    missed_by_both: dict[str, int],
    phase_counts: dict[str, dict[str, int]],
    burst_rows: list[_BurstFloorRow],
    episode_level: dict[str, _EpisodeLevelStats],
    missed_window_stats: dict[str, _MissedWindowStats],
    sensitivity: dict[str, tuple[_ConfusionCounts, _ConfusionCounts]],
    detectors: tuple[str, ...],
) -> str:
    lines = [
        f"# Per-fault-type and per-phase breakdown -- `{dataset_version}`",
        "",
        "> **Diagnosis only, not for the thesis.** Regenerated from "
        "`ml/harness/evaluate.py --save-predictions` output; see "
        f"`docs/results/results-{dataset_version}.md` for the headline numbers.",
        "",
        "## a) Per fault type",
        "",
        "`episodes`/`detected` are resource-occurrence counts, matching "
        "`results-v6.md`'s per-shape table convention -- an episode affecting "
        "multiple resources (`region_down`) is counted once per affected "
        "resource, so these totals reconcile with that table rather than with "
        "a plain count of distinct episodes.",
        "",
        "| Fault type | Detector | Episodes | Recall | Delay p50 | Delay p95 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for fault_type in sorted(fault_type_stats):
        for detector in detectors:
            s = fault_type_stats[fault_type].get(detector, _FaultTypeStats())
            recall = s.detected / s.episodes if s.episodes else float("nan")
            lines.append(
                f"| `{fault_type}` | `{detector}` | {s.episodes} | {_fmt(recall)} "
                f"| {_fmt_s(_percentile(s.delays_s, 50))} | {_fmt_s(_percentile(s.delays_s, 95))} |"
            )

    lines += [
        "",
        "Episodes missed by **both** detectors (deduplicated by episode id, "
        "unlike the table above):",
        "",
        "| Fault type | Missed by both |",
        "| --- | --- |",
    ]
    for fault_type in sorted(missed_by_both):
        lines.append(f"| `{fault_type}` | {missed_by_both[fault_type]} |")

    lines += [
        "",
        "## b) False alarms by phase",
        "",
        "`ramp`/`fault` cannot appear here by construction -- a false alarm is, "
        "by definition, a breach on a ground-truth-normal window, and those two "
        "phases only ever apply to a window already inside a labelled fault. "
        "Zero in those columns is the expected, structural answer, not a gap "
        "in the data.",
        "",
        "| Detector | Normal | Ramp | Recovery | Other | Total |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for detector in detectors:
        counts = phase_counts.get(detector, dict.fromkeys(PHASES, 0))
        total = sum(counts.values())
        cells = " | ".join(
            f"{counts[p]} ({counts[p] / total:.0%})" if total else "0 (n/a)" for p in PHASES
        )
        lines.append(f"| `{detector}` | {cells} | {total} |")

    lines += [""]
    for detector in detectors:
        counts = phase_counts.get(detector, dict.fromkeys(PHASES, 0))
        total = sum(counts.values())
        lines.append(
            f"- `{detector}`: {total} false alarm(s) total -- "
            f"{counts['normal']} in `normal`, {counts['recovery']} in `recovery`."
        )

    lines += [
        "",
        "## c) Intermittent bursts vs the hysteresis floor",
        "",
        f"`{CONSECUTIVE_BREACHES_REQUIRED}` consecutive breaches are required to "
        "detect anything, so a burst shorter than that many collector steps is "
        "structurally undetectable regardless of score; a burst of exactly "
        f"`{CONSECUTIVE_BREACHES_REQUIRED}` steps has no slack at all -- every "
        "single step of it must breach, or the burst is missed.",
        "",
        "| Episode | Burst length | Steps | vs floor | Caught by |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in sorted(burst_rows, key=lambda r: r.episode):
        caught = ", ".join(f"`{d}`" for d in row.caught_by) or "neither"
        lines.append(
            f"| {row.episode} | {row.burst_seconds:.0f}s | {row.burst_steps:.1f} "
            f"| {row.bucket} | {caught} |"
        )

    below = sum(1 for r in burst_rows if r.bucket == "below_floor")
    at = [r for r in burst_rows if r.bucket == "at_floor"]
    at_caught = sum(1 for r in at if r.caught_by)
    lines += [
        "",
        f"{below} burst(s) below the floor (structurally uncatchable); "
        f"{len(at)} at the floor, of which {at_caught} were actually caught "
        "(zero tolerance for a missed step within the burst); "
        f"{sum(1 for r in burst_rows if r.bucket == 'above_floor')} above the "
        "floor with at least one step of slack.",
        "",
        "## d) Episode-level view",
        "",
        "`occurrences`/`detected` are resource-occurrence counts (same "
        "convention as section a), summed across fault types.",
        "",
        "| Detector | Fault occurrences | Detected | Share detected |",
        "| --- | --- | --- | --- |",
    ]
    for detector in detectors:
        episode_stats = episode_level.get(detector, _EpisodeLevelStats())
        share = (
            episode_stats.detected / episode_stats.occurrences
            if episode_stats.occurrences
            else float("nan")
        )
        lines.append(
            f"| `{detector}` | {episode_stats.occurrences} | {episode_stats.detected} "
            f"| {_fmt(share)} |"
        )

    lines += [
        "",
        f"Of all missed (false-negative) windows, how many sit in the first "
        f"`{CONSECUTIVE_BREACHES_REQUIRED - 1}` true-label windows of a fault at "
        "their resource -- unavoidable under the 3-consecutive-breach rule, since "
        "no alarm can fire before the counter reaches the gate -- versus a later "
        "window, which the detector had a real chance at:",
        "",
        "| Detector | Missed windows | Unavoidable (first "
        f"{CONSECUTIVE_BREACHES_REQUIRED - 1}) | Later |",
        "| --- | --- | --- | --- |",
    ]
    for detector in detectors:
        m = missed_window_stats.get(detector, _MissedWindowStats())
        total = m.unavoidable + m.later
        lines.append(f"| `{detector}` | {total} | {m.unavoidable} | {m.later} |")

    lines += [
        "",
        "## e) Recovery-excluded sensitivity analysis",
        "",
        "> Post-hoc sensitivity analysis. Not the Gate B metric. Recovery "
        "windows are labelled normal in the official evaluation; this view "
        "excludes them to show where false alarms come from.",
        "",
        "| Detector | View | Precision | Recall | F1 | FPR |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for detector in detectors:
        official, excl_recovery = sensitivity.get(
            detector, (_ConfusionCounts(), _ConfusionCounts())
        )
        for label, confusion in (("official", official), ("excl. recovery", excl_recovery)):
            precision, recall, f1, fpr = _prf(confusion)
            lines.append(
                f"| `{detector}` | {label} | {_fmt(precision)} | {_fmt(recall)} "
                f"| {_fmt(f1)} | {_fmt(fpr)} |"
            )
    lines.append("")
    return "\n".join(lines)


def run(dataset_version: str, root: Path, detectors: tuple[str, ...]) -> str:
    manifest = load_manifest(dataset_version, root)
    intervals_by_resource = load_fault_intervals(dataset_version, root)
    episode_meta = _episode_meta(intervals_by_resource)
    step_seconds = float(manifest["virtual_clock"]["step_seconds"])
    window_samples = int(manifest["window_samples"])
    grace = timedelta(seconds=step_seconds * (window_samples - 1))

    predictions: dict[str, list[_Row]] = {}
    for detector in detectors:
        path = dataset_dir(dataset_version, root) / f"predictions-{detector}.jsonl"
        if not path.exists():
            raise FileNotFoundError(
                f"no {path}. Run `python -m ml.harness.evaluate --dataset-version "
                f"{dataset_version} --save-predictions --detectors {' '.join(detectors)}` first."
            )
        predictions[detector] = _load_predictions(path)

    fault_type_stats, seen_ids, detected_ids = analyze_fault_types(
        predictions, intervals_by_resource, episode_meta, grace
    )
    ground_truth_ids = seen_ids[detectors[0]]
    missed_by_both: dict[str, int] = defaultdict(int)
    for episode in ground_truth_ids:
        if all(episode not in detected_ids.get(d, set()) for d in detectors):
            missed_by_both[episode_meta[episode].fault_type] += 1

    phase_counts = {d: false_alarms_by_phase(rows) for d, rows in predictions.items()}
    burst_rows = intermittent_floor_analysis(
        episode_meta, ground_truth_ids, detected_ids, step_seconds, detectors
    )

    episode_level = analyze_episode_level(fault_type_stats, detectors)
    missed_window_stats = {d: missed_window_split(rows) for d, rows in predictions.items()}
    sensitivity = recovery_excluded_sensitivity(predictions)

    return render_markdown(
        dataset_version,
        fault_type_stats,
        dict(missed_by_both),
        phase_counts,
        burst_rows,
        episode_level,
        missed_window_stats,
        sensitivity,
        detectors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-fault-type and per-phase breakdown from exported predictions."
    )
    parser.add_argument("--dataset-version", default="v6")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--detectors", nargs="+", default=list(DETECTORS))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.out is None:
        args.out = Path(f"docs/results/breakdown-{args.dataset_version}.md")

    markdown = run(args.dataset_version, args.dataset_root, tuple(args.detectors))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
