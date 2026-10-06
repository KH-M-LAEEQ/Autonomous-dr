"""Tests for ml/detectors/iforest.py.

Skipped wholesale when the `ml` extra is not installed -- `ml/detectors/
__init__.py` only registers this detector if numpy/scikit-learn import.
"""

from __future__ import annotations

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
