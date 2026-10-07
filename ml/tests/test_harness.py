"""Tests for ml/harness/evaluate.py."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import ml.harness.evaluate as evaluate_module
from core.interfaces.anomaly_detector import AnomalyDetector
from core.models.domain import MetricWindow
from ml.harness.evaluate import (
    EvalResult,
    FaultInterval,
    _fault_at,
    _grace_fault_at,
    _percentile,
    evaluate,
    load_fault_intervals,
    load_manifest,
    load_windows_for_resource,
    time_based_split,
)

# -- split (the original regression guards) --------------------------------


def test_split_is_chronological_and_disjoint() -> None:
    train, val, test = time_based_split(100, 0.7, 0.15)
    assert train == slice(0, 70)
    assert val == slice(70, 85)
    assert test == slice(85, 100)


def test_split_never_shuffles() -> None:
    """Regression guard for the single worst mistake available in this project."""
    train, val, test = time_based_split(1000)
    assert train.stop == val.start
    assert val.stop == test.start


# -- percentiles -----------------------------------------------------------


def test_percentile_of_empty_is_nan_not_zero() -> None:
    """A detector that never fired has no delay distribution. Zero would read
    as "instant detection", which is the opposite of the truth."""
    assert math.isnan(_percentile([], 50))


def test_percentile_of_one_sample() -> None:
    assert _percentile([42.0], 99) == 42.0


def test_percentile_interpolates() -> None:
    assert _percentile([0.0, 10.0], 50) == pytest.approx(5.0)
    assert _percentile([0.0, 1.0, 2.0, 3.0], 100) == 3.0


# -- labelling convention --------------------------------------------------


def _window(end: datetime, step_seconds: int = 10, samples: int = 12) -> MetricWindow:
    return MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=end - timedelta(seconds=step_seconds * (samples - 1)),
        end=end,
        step_seconds=step_seconds,
        values={"cpu_percent": [30.0] * samples},
    )


_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_INTERVAL = [
    FaultInterval(
        episode=0,
        fault_type="cpu_hog",
        start=_T0 + timedelta(seconds=100),
        end=_T0 + timedelta(seconds=200),
    )
]


def test_window_is_anomalous_when_its_last_sample_is_in_the_fault() -> None:
    assert _fault_at(_window(_T0 + timedelta(seconds=150)), _INTERVAL) is not None


def test_window_ending_exactly_at_fault_start_is_anomalous() -> None:
    assert _fault_at(_window(_T0 + timedelta(seconds=100)), _INTERVAL) is not None


def test_window_ending_exactly_at_fault_end_is_normal() -> None:
    """The interval is half-open [start, end), so the window whose last sample
    lands on `end` is already recovered."""
    assert _fault_at(_window(_T0 + timedelta(seconds=200)), _INTERVAL) is None


def test_window_overlapping_the_fault_only_in_its_history_is_normal() -> None:
    """Last-sample labelling, not any-overlap: this window's 12 samples reach
    back into the fault, but its latest reading is recovered."""
    window = _window(_T0 + timedelta(seconds=260))
    assert window.start < _INTERVAL[0].end
    assert _fault_at(window, _INTERVAL) is None


def test_window_before_the_fault_is_normal() -> None:
    assert _fault_at(_window(_T0 + timedelta(seconds=50)), _INTERVAL) is None


# -- dataset loading + end-to-end evaluate ---------------------------------


def _write_dataset(root: Path, resources: list[str], n_normal: int = 60) -> None:
    """A tiny two-resource dataset: a long normal stretch, one fault near the
    end so it lands in the test slice, then recovery."""
    out = root / "vtest"
    out.mkdir(parents=True)
    step, samples = 10, 12
    fault_start_tick = int(n_normal * 0.90)
    fault_ticks = 6

    rows: list[dict] = []
    for tick in range(n_normal):
        end = _T0 + timedelta(seconds=step * tick)
        faulty = fault_start_tick <= tick < fault_start_tick + fault_ticks
        for rid in resources:
            cpu = 97.0 if faulty else 30.0
            rows.append(
                {
                    "resource_id": rid,
                    "tenant_id": "t1",
                    "region": "sim-us-east-1",
                    "kind": "web_service",
                    "start": (end - timedelta(seconds=step * (samples - 1))).isoformat(),
                    "end": end.isoformat(),
                    "step_seconds": step,
                    "values": {"cpu_percent": [cpu] * samples},
                }
            )
    (out / "windows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    label = {
        "episode": 0,
        "shape": "test_shape",
        "fault_type": "region_down",
        "target": resources[0],
        "tenant_id": "t1",
        "region": "sim-us-east-1",
        "affected": resources,
        "start": (_T0 + timedelta(seconds=step * fault_start_tick)).isoformat(),
        "end": (_T0 + timedelta(seconds=step * (fault_start_tick + fault_ticks))).isoformat(),
        "duration_seconds": step * fault_ticks,
    }
    (out / "labels.jsonl").write_text(json.dumps(label) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"version": "vtest", "seed": 3, "resources": resources}), encoding="utf-8"
    )


def test_load_fault_intervals_expands_every_affected_resource(tmp_path: Path) -> None:
    """A region_down label must produce an interval for each affected resource,
    not only the injection target -- otherwise collateral detections on the
    other resources in the region score as false positives."""
    _write_dataset(tmp_path, ["r1", "r2"])
    intervals = load_fault_intervals("vtest", tmp_path)
    assert set(intervals) == {"r1", "r2"}
    assert intervals["r1"][0].fault_type == "region_down"
    assert intervals["r1"][0].start == intervals["r2"][0].start


def test_load_windows_for_resource_filters_and_sorts(tmp_path: Path) -> None:
    _write_dataset(tmp_path, ["r1", "r2"])
    windows = load_windows_for_resource("vtest", "r2", tmp_path)
    assert windows
    assert all(w.resource_id == "r2" for w in windows)
    assert windows == sorted(windows, key=lambda w: w.end)


def test_load_manifest_reads_the_version(tmp_path: Path) -> None:
    _write_dataset(tmp_path, ["r1"])
    assert load_manifest("vtest", tmp_path)["version"] == "vtest"


def test_missing_dataset_raises_with_a_usable_message(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make_episodes"):
        load_manifest("nope", tmp_path)


def test_evaluate_returns_a_populated_result(tmp_path: Path) -> None:
    _write_dataset(tmp_path, ["r1", "r2"])
    result = evaluate("threshold", "vtest", tmp_path)

    assert isinstance(result, EvalResult)
    assert result.detector == "threshold"
    assert result.dataset_version == "vtest"
    assert result.seed == 3
    assert "not for the thesis" in result.notes
    # Counts must account for every scored window exactly once.
    e = result.extra
    total = e["true_positives"] + e["false_positives"] + e["true_negatives"] + e["false_negatives"]
    assert total == e["test_windows"]
    assert 0.0 <= result.precision <= 1.0
    assert 0.0 <= result.recall <= 1.0
    assert 0.0 <= result.false_positive_rate <= 1.0


def test_evaluate_reports_p99_delay_field(tmp_path: Path) -> None:
    """p99 is part of the row, so a run with no detections still reports it as
    nan rather than omitting the column."""
    _write_dataset(tmp_path, ["r1"])
    result = evaluate("threshold", "vtest", tmp_path)
    assert hasattr(result, "detection_delay_p99_s")
    delay = result.detection_delay_p99_s
    assert math.isnan(delay) or delay >= 0.0


def test_evaluate_reports_a_per_shape_breakdown(tmp_path: Path) -> None:
    """Pooled numbers hide the thing worth knowing, so each shape gets its own
    row keyed by `labels.jsonl`'s `shape`."""
    _write_dataset(tmp_path, ["r1", "r2"])
    result = evaluate("threshold", "vtest", tmp_path)
    assert set(result.by_shape) == {"test_shape"}
    row = result.by_shape["test_shape"]
    assert row["episodes"] >= 1
    assert row["detected"] <= row["episodes"]
    assert 0.0 <= row["detection_rate"] <= 1.0
    assert set(row) >= {"delay_p50_s", "delay_p95_s", "delay_p99_s"}


def test_shape_falls_back_to_fault_type_for_pre_shape_datasets(tmp_path: Path) -> None:
    """v1-v3 predate shapes. Their labels must still group, not crash."""
    _write_dataset(tmp_path, ["r1"])
    labels_path = tmp_path / "vtest" / "labels.jsonl"
    rows = [json.loads(line) for line in labels_path.read_text().splitlines() if line.strip()]
    for row in rows:
        row.pop("shape")
    labels_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    intervals = load_fault_intervals("vtest", tmp_path)
    assert intervals["r1"][0].shape == "region_down"


def test_evaluate_trains_only_on_normal_windows(tmp_path: Path) -> None:
    """The fault sits in the last 10% of the timeline, so it is outside the
    70% train slice; train_windows must therefore equal the full train slice."""
    _write_dataset(tmp_path, ["r1"])
    result = evaluate("threshold", "vtest", tmp_path)
    windows = load_windows_for_resource("vtest", "r1", tmp_path)
    train_slice, _, _ = time_based_split(len(windows))
    assert result.extra["train_windows"] == len(windows[train_slice])


# -- zero-second detection delays: episode reset + grace period ------------
#
# Isolation Forest reported a 0s detection delay on `intermittent`'s back-to-
# back bursts. Root cause: the detector's consecutive-breach counter is
# per-instance, scored across the whole test slice for one resource, and was
# never reset between episodes. A breach streak that built up near the tail
# of one burst (where the rolling-window features still carry some
# fault-contaminated samples) only needed one more breach on the very first
# window of the *next* burst to "detect" it instantly. These tests pin the
# fix: `_score_resource` resets the detector at each new episode's strict
# start, and `_grace_fault_at` gives a lingering breach the chance to be
# credited to the episode it actually describes instead of the next one.


class _ScriptedDetector(AnomalyDetector):
    """Hand-scripted hysteresis for regression-testing the harness's episode
    bookkeeping -- not a real scorer. `breaches` is the exact True/False
    sequence to feed `is_anomaly`, one entry per call, in call order; it must
    have exactly as many entries as there are test-slice windows."""

    name = "scripted"
    requires_training = True

    def __init__(self, breaches: list[bool]) -> None:
        self._breaches = breaches
        self._call = 0
        self._consecutive_breaches = 0

    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        pass

    def score(self, window: MetricWindow) -> float:
        return 1.0 if self._breaches[self._call] else 0.0

    def explain(self) -> dict[str, object]:
        return {}

    def is_anomaly(self, window: MetricWindow) -> bool:
        breach = self._breaches[self._call]
        self._call += 1
        self._consecutive_breaches = self._consecutive_breaches + 1 if breach else 0
        return self._consecutive_breaches >= 3

    def reset(self) -> None:
        self._consecutive_breaches = 0


def _write_scripted_dataset(
    root: Path, version: str, intervals: list[tuple[int, int, int]], n_total: int = 100
) -> None:
    """One resource, `n_total` windows, step 10s, 12 samples -- and a fault
    interval per `(episode, start_tick, end_tick)` in `intervals`. Values are
    constant; `_ScriptedDetector` ignores them entirely."""
    out = root / version
    out.mkdir(parents=True)
    step, samples = 10, 12

    rows = [
        {
            "resource_id": "r1",
            "tenant_id": "t1",
            "region": "sim-us-east-1",
            "kind": "web_service",
            "start": (
                _T0 + timedelta(seconds=step * tick) - timedelta(seconds=step * (samples - 1))
            ).isoformat(),
            "end": (_T0 + timedelta(seconds=step * tick)).isoformat(),
            "step_seconds": step,
            "values": {"cpu_percent": [30.0] * samples},
        }
        for tick in range(n_total)
    ]
    (out / "windows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    labels = [
        {
            "episode": episode,
            "shape": "test_shape",
            "fault_type": "cpu_hog",
            "target": "r1",
            "tenant_id": "t1",
            "region": "sim-us-east-1",
            "affected": ["r1"],
            "start": (_T0 + timedelta(seconds=step * start_tick)).isoformat(),
            "end": (_T0 + timedelta(seconds=step * end_tick)).isoformat(),
            "duration_seconds": step * (end_tick - start_tick),
        }
        for episode, start_tick, end_tick in intervals
    ]
    (out / "labels.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in labels), encoding="utf-8"
    )
    (out / "manifest.json").write_text(
        json.dumps({"version": version, "seed": 7, "resources": ["r1"]}), encoding="utf-8"
    )


def _evaluate_scripted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, version: str, breaches: list[bool]
) -> EvalResult:
    monkeypatch.setattr(
        evaluate_module, "build", lambda name, **kwargs: _ScriptedDetector(**kwargs)
    )
    return evaluate_module.evaluate("scripted", version, tmp_path, breaches=breaches)


def test_grace_fault_at_only_covers_the_tail_after_an_interval_ends() -> None:
    grace = timedelta(seconds=50)
    assert _grace_fault_at(_window(_T0 + timedelta(seconds=199)), _INTERVAL, grace) is None
    assert _grace_fault_at(_window(_T0 + timedelta(seconds=200)), _INTERVAL, grace) is not None
    assert _grace_fault_at(_window(_T0 + timedelta(seconds=249)), _INTERVAL, grace) is not None
    assert _grace_fault_at(_window(_T0 + timedelta(seconds=250)), _INTERVAL, grace) is None


def test_grace_fault_at_is_disabled_by_a_non_positive_grace() -> None:
    assert _grace_fault_at(_window(_T0 + timedelta(seconds=210)), _INTERVAL, timedelta(0)) is None


def test_episode_reset_prevents_a_carried_over_breach_from_zeroing_the_next_delay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test slice is ticks 85-99 (15 windows, local 0-14). Episode A: ticks
    91-93 (3 clean consecutive breaches -> detected at tick 93, delay 20s).
    Then breaches keep firing through ticks 94-96 -- A's grace tail, still
    unresolved when episode B's window actually arrives. Episode B starts at
    tick 97: WITHOUT a reset there, the carried-over count of >=3 would fire
    on B's very first window, delay 0s. WITH the reset, B needs its own 3
    consecutive breaches (ticks 97-99), delay 20s -- never 0."""
    breaches = [False] * 6 + [True] * 3 + [True] * 3 + [True] * 3
    assert len(breaches) == 15  # one entry per test-slice window (ticks 85-99)

    _write_scripted_dataset(tmp_path, "vreset", intervals=[(0, 91, 94), (1, 97, 999)], n_total=100)
    result = _evaluate_scripted(monkeypatch, tmp_path, "vreset", breaches)

    assert result.extra["episodes_detected"] == 2
    # Both episodes must be caught at the same, non-zero, 2-step floor. With
    # only 2 delay samples, p50 and p95 both landing on 20.0 is only possible
    # if BOTH are 20.0 -- one of them being 0.0 would pull the percentiles
    # off of 20 (e.g. [0, 20] interpolates to p50=10, p95=19).
    assert result.detection_delay_p50_s == pytest.approx(20.0)
    assert result.detection_delay_p95_s == pytest.approx(20.0)


def test_breach_before_fault_start_is_a_false_alarm_not_a_catch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """3 consecutive breaches entirely before the fault starts (ticks 85-87)
    cross the hysteresis gate once, on the 3rd of the three -- that single
    window must score as a false positive and must NOT shorten the real
    episode's delay when the fault later begins cleanly at tick 95."""
    breaches = [True, True, True] + [False] * 7 + [True, True, True] + [False, False]
    assert len(breaches) == 15

    _write_scripted_dataset(tmp_path, "vearly", intervals=[(0, 95, 98)], n_total=100)
    result = _evaluate_scripted(monkeypatch, tmp_path, "vearly", breaches)

    assert result.extra["false_positives"] == 1
    assert result.extra["episodes_detected"] == 1
    assert result.extra["delay_samples"] == 1
    assert result.detection_delay_p50_s == pytest.approx(20.0)
