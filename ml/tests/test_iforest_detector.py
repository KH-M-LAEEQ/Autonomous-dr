"""Tests for ml/detectors/iforest.py.

Skipped wholesale when the `ml` extra is not installed -- `ml/detectors/
__init__.py` only registers this detector if numpy/scikit-learn import.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from core.models.domain import MetricWindow
from ml.detectors import REGISTRY, build

pytest.importorskip("sklearn", reason="requires the `ml` extra")

from ml.detectors.iforest import IsolationForestDetector


def _window(cpu: float, latency: float = 120.0, rng: random.Random | None = None) -> MetricWindow:
    r = rng or random.Random(0)
    now = datetime.now(UTC)
    return MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values={
            "cpu_percent": [cpu + r.gauss(0, 1.0) for _ in range(12)],
            "latency_p95": [latency + r.gauss(0, 8.0) for _ in range(12)],
        },
    )


def _normal_windows(n: int = 200, seed: int = 7) -> list[MetricWindow]:
    rng = random.Random(seed)
    return [_window(30.0, rng=rng) for _ in range(n)]


def _fitted() -> IsolationForestDetector:
    detector = build("iforest")
    assert isinstance(detector, IsolationForestDetector)
    detector.fit(_normal_windows())
    return detector


def test_registered_under_iforest_name() -> None:
    assert "iforest" in REGISTRY
    detector = build("iforest")
    assert isinstance(detector, IsolationForestDetector)
    assert detector.name == "iforest"
    assert detector.requires_training is True


def test_fit_sets_the_iqr_cutoff() -> None:
    detector = _fitted()
    # 0.5 is the pre-fit class default; fit must replace it.
    assert detector.decision_threshold != 0.5


def test_fit_rejects_too_few_windows() -> None:
    detector = build("iforest")
    with pytest.raises(ValueError, match="at least 2 training windows"):
        detector.fit([_window(30.0)])


def test_fit_rejects_signal_free_windows() -> None:
    now = datetime.now(UTC)
    empty = MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values={},
    )
    detector = build("iforest")
    with pytest.raises(ValueError, match="no detector signals"):
        detector.fit([empty, empty])


def test_score_before_fit_raises() -> None:
    detector = build("iforest")
    with pytest.raises(RuntimeError, match="fit\\(\\) must be called"):
        detector.score(_window(30.0))


def test_anomalous_window_scores_above_normal() -> None:
    detector = _fitted()
    assert detector.score(_window(97.0)) > detector.score(_window(30.0))


def test_normal_readings_never_trip() -> None:
    detector = _fitted()
    rng = random.Random(99)
    for _ in range(10):
        assert detector.is_anomaly(_window(30.0, rng=rng)) is False


def test_requires_three_consecutive_breaches() -> None:
    detector = _fitted()
    assert detector.is_anomaly(_window(97.0)) is False  # 1st breach
    assert detector.is_anomaly(_window(98.0)) is False  # 2nd breach
    assert detector.is_anomaly(_window(99.0)) is True  # 3rd -- trips


def test_a_normal_reading_resets_the_breach_counter() -> None:
    detector = _fitted()
    assert detector.is_anomaly(_window(97.0)) is False
    assert detector.is_anomaly(_window(98.0)) is False
    assert detector.is_anomaly(_window(30.0)) is False  # back to normal -- resets
    assert detector.is_anomaly(_window(97.0)) is False  # breach count is back to 1


def test_hysteresis_is_configurable_for_harness_comparisons() -> None:
    detector = build("iforest", consecutive_breaches_required=1)
    assert isinstance(detector, IsolationForestDetector)
    detector.fit(_normal_windows())
    assert detector.is_anomaly(_window(97.0)) is True  # trips on the first breach


def test_explain_describes_the_last_score_and_never_raises() -> None:
    detector = _fitted()
    assert detector.explain()["detector"] == "iforest"  # before any score() call
    detector.is_anomaly(_window(97.0))
    explanation = detector.explain()
    assert explanation["detector"] == "iforest"
    assert explanation["consecutive_breaches"] == 1
    assert explanation["breaches_required"] == 3
    assert explanation["score"] > 0
    assert explanation["top_deviating_signals"][0]["signal"] == "cpu_percent"


def test_missing_signal_is_filled_with_the_training_mean_not_zero() -> None:
    """Absent means "no reading", not 0.0 -- zero-filling would hand the forest
    an outlier the training data never contained."""
    detector = _fitted()
    now = datetime.now(UTC)
    partial = MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values={"cpu_percent": [30.0] * 12},  # latency_p95 absent entirely
    )
    vector = detector._vector(partial)
    latency_mean = detector._train_mean["latency_p95"]
    # The three latency features are mean/std/last; mean and last take the
    # training mean, which is nowhere near zero.
    assert latency_mean > 100.0
    assert vector[3] == pytest.approx(latency_mean)
    assert vector[5] == pytest.approx(latency_mean)


def test_fit_is_reproducible_for_a_fixed_random_state() -> None:
    a, b = build("iforest", random_state=5), build("iforest", random_state=5)
    assert isinstance(a, IsolationForestDetector)
    assert isinstance(b, IsolationForestDetector)
    train = _normal_windows()
    a.fit(train)
    b.fit(train)
    probe = _window(97.0)
    assert a.score(probe) == pytest.approx(b.score(probe))
    assert a.decision_threshold == pytest.approx(b.decision_threshold)


def test_reset_clears_an_in_progress_breach_streak() -> None:
    """`reset()` is a duck-typed extension the Week 10 harness calls between
    fault episodes (see ml/harness/evaluate.py and
    docs/results/practice-run.md, "zero-second detection delays") -- not part
    of the frozen `AnomalyDetector` interface. A streak that would trip on
    its next breach must need all 3 again after a reset."""
    detector = _fitted()
    assert detector.is_anomaly(_window(97.0)) is False  # 1st breach
    assert detector.is_anomaly(_window(98.0)) is False  # 2nd breach
    detector.reset()
    assert detector.is_anomaly(_window(99.0)) is False  # back to 1st, not 3rd
    assert detector.is_anomaly(_window(99.0)) is False  # 2nd
    assert detector.is_anomaly(_window(99.0)) is True  # 3rd -- now it trips


# -- batch scoring -----------------------------------------------------------


def test_score_batch_matches_calling_score_one_at_a_time() -> None:
    """The whole point of `score_batch`: identical numbers, in the same
    order, to scoring each window individually -- just one sklearn call
    instead of many."""
    rng = random.Random(3)
    probe_windows = [_window(cpu, rng=rng) for cpu in (30.0, 97.0, 45.0, 30.0, 85.0)]

    one_at_a_time = _fitted()
    sequential_scores = [one_at_a_time.score(w) for w in probe_windows]

    batched = _fitted()
    batch_scores = batched.score_batch(probe_windows)

    assert batch_scores == pytest.approx(sequential_scores)


def test_score_batch_of_empty_list_is_empty() -> None:
    assert _fitted().score_batch([]) == []


def test_score_batch_requires_fit_first() -> None:
    detector = build("iforest")
    assert isinstance(detector, IsolationForestDetector)
    with pytest.raises(RuntimeError, match="fit"):
        detector.score_batch([_window(30.0)])


def test_is_breach_replayed_over_batch_scores_matches_is_anomaly() -> None:
    """`is_breach` is the hysteresis `is_anomaly` does internally, minus the
    re-scoring -- replaying it over `score_batch`'s output must reach the
    exact same True/False sequence as calling `is_anomaly` window by
    window, breach-for-breach."""
    rng = random.Random(11)
    probe_windows = [
        _window(cpu, rng=rng) for cpu in (30.0, 97.0, 98.0, 99.0, 30.0, 30.0, 96.0, 97.0, 98.0)
    ]

    sequential = _fitted()
    sequential_results = [sequential.is_anomaly(w) for w in probe_windows]

    batched = _fitted()
    scores = batched.score_batch(probe_windows)
    batched_results = [batched.is_breach(s) for s in scores]

    assert batched_results == sequential_results
    assert any(batched_results)  # the scripted CPU spikes must trip it at least once


def test_explain_after_score_batch_describes_the_last_window() -> None:
    detector = _fitted()
    windows = [_window(30.0), _window(97.0)]
    detector.score_batch(windows)
    explanation = detector.explain()
    assert explanation["score"] == pytest.approx(detector.score_batch([windows[-1]])[0])


# -- time-of-day (optional, off by default) --------------------------------


def _window_at(hour: int, minute: int = 0, cpu: float = 30.0) -> MetricWindow:
    end = datetime(2026, 1, 1, hour, minute, 0, tzinfo=UTC)
    return MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=end - timedelta(seconds=110),
        end=end,
        step_seconds=10,
        values={"cpu_percent": [cpu] * 12},
    )


def test_time_of_day_is_off_by_default() -> None:
    detector = build("iforest")
    assert isinstance(detector, IsolationForestDetector)
    assert detector._use_time_of_day is False
    detector.fit(_normal_windows())
    # 2 training signals (cpu_percent, latency_p95) x 3 summary features,
    # no sin/cos appended.
    assert len(detector._vector(_window_at(14))) == 6


def test_time_of_day_appends_sin_cos_features_when_enabled() -> None:
    detector = build("iforest", use_time_of_day=True)
    assert isinstance(detector, IsolationForestDetector)
    detector.fit(_normal_windows())
    vector = detector._vector(_window_at(hour=6, minute=0))  # 06:00 = quarter day
    assert len(vector) == 8  # 2 signals x 3 summary features + sin + cos
    assert vector[-2] == pytest.approx(1.0, abs=1e-9)  # sin(2*pi*0.25) == 1
    assert vector[-1] == pytest.approx(0.0, abs=1e-9)  # cos(2*pi*0.25) == 0


def test_time_of_day_midnight_and_just_before_are_close_in_feature_space() -> None:
    """The whole point of sin/cos over a raw hour-of-day integer: 23:59 and
    00:00 are adjacent on the clock and must land close together, not at
    opposite ends of a 0-23 range."""
    detector = build("iforest", use_time_of_day=True)
    assert isinstance(detector, IsolationForestDetector)
    detector.fit(_normal_windows())
    midnight = detector._time_of_day_features(_window_at(hour=0, minute=0))
    just_before = detector._time_of_day_features(_window_at(hour=23, minute=59))
    distance = math.dist(midnight, just_before)
    far_apart = math.dist(midnight, detector._time_of_day_features(_window_at(hour=12)))
    assert distance < far_apart


def test_time_of_day_does_not_change_the_threshold_detector() -> None:
    """The switch lives entirely on `IsolationForestDetector`; `ThresholdDetector`
    takes no such kwarg and must stay untouched."""
    from ml.detectors.threshold import ThresholdDetector

    assert "use_time_of_day" not in ThresholdDetector.__init__.__code__.co_varnames
