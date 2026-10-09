"""Tests for ml/detectors/threshold.py -- the permanent Week 4 baseline."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from core.models.domain import MetricWindow
from ml.detectors import build
from ml.detectors.threshold import CONSECUTIVE_BREACHES_REQUIRED, ThresholdDetector


def _window(value: float, signal: str = "cpu_pct") -> MetricWindow:
    now = datetime.now(UTC)
    return MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=10),
        end=now,
        step_seconds=10,
        values={signal: [value]},
    )


def _fitted_detector(seed: int = 1) -> ThresholdDetector:
    rng = random.Random(seed)
    detector = build("threshold")
    assert isinstance(detector, ThresholdDetector)
    train = [_window(30.0 + rng.gauss(0, 3)) for _ in range(200)]
    detector.fit(train)
    return detector


def test_registered_under_threshold_name() -> None:
    detector = build("threshold")
    assert isinstance(detector, ThresholdDetector)
    assert detector.name == "threshold"


def test_normal_readings_never_trip() -> None:
    detector = _fitted_detector()
    for value in (31.0, 29.0, 32.0, 28.0, 30.5):
        assert detector.is_anomaly(_window(value)) is False


def test_requires_three_consecutive_breaches() -> None:
    detector = _fitted_detector()
    assert detector.is_anomaly(_window(95.0)) is False  # 1st breach
    assert detector.is_anomaly(_window(96.0)) is False  # 2nd breach
    assert detector.is_anomaly(_window(97.0)) is True  # 3rd -- trips


def test_a_normal_reading_resets_the_breach_counter() -> None:
    detector = _fitted_detector()
    assert detector.is_anomaly(_window(95.0)) is False
    assert detector.is_anomaly(_window(96.0)) is False
    assert detector.is_anomaly(_window(30.0)) is False  # back to normal -- resets
    assert detector.is_anomaly(_window(95.0)) is False  # breach count is back to 1
    assert detector.is_anomaly(_window(96.0)) is False


def test_consecutive_breaches_required_is_three() -> None:
    assert CONSECUTIVE_BREACHES_REQUIRED == 3


def test_explain_reports_the_offending_signal() -> None:
    detector = _fitted_detector()
    detector.is_anomaly(_window(95.0))
    explanation = detector.explain()
    assert explanation["detector"] == "threshold"
    assert explanation["signal"] == "cpu_pct"
    assert explanation["consecutive_breaches"] == 1
