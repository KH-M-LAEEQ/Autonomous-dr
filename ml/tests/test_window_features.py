"""Guard test for ml/detectors/window_features.py.

`WindowVectorizer` is a standalone copy of `IsolationForestDetector`'s
vectorization logic, kept separate because `iforest.py` has tests that poke
its private `_vector`/`_train_mean`/`_time_of_day_features` attributes
directly (see `ml/tests/test_iforest_detector.py` and
`ml/detectors/window_features.py`'s module docstring for why it's a copy, not
an import). A copy that silently drifts from the original defeats the whole
point of the PyOD family seeing "precisely what Isolation Forest sees" -- so
this test fits both on the same windows and asserts their outputs agree,
instead of just asserting it in a docstring.

`IsolationForestDetector` is imported locally inside each test (never at
module level), guarded by `pytest.importorskip` first -- same pattern as
`ml/tests/test_pyod_detector.py` and
`ml/tests/test_harness.py::test_batch_scoring_produces_identical_results_to_per_window_scoring`.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from core.models.domain import MetricWindow
from ml.detectors.window_features import WindowVectorizer

if TYPE_CHECKING:
    from ml.detectors.iforest import IsolationForestDetector


def _iforest_detector_class() -> type[IsolationForestDetector]:
    pytest.importorskip("sklearn", reason="requires the `ml` extra")
    from ml.detectors.iforest import IsolationForestDetector as _IsolationForestDetector

    return _IsolationForestDetector


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


def _normal_windows(n: int = 60, seed: int = 7) -> list[MetricWindow]:
    rng = random.Random(seed)
    return [_window(30.0, rng=rng) for _ in range(n)]


def test_vector_matches_iforest_without_time_of_day() -> None:
    IsolationForestDetector = _iforest_detector_class()
    train = _normal_windows()

    reference = IsolationForestDetector()
    reference.fit(train)

    vectorizer = WindowVectorizer()
    vectorizer.fit(train)

    for probe in (_window(30.0), _window(97.0), _window_at(hour=14)):
        assert vectorizer.vector(probe) == pytest.approx(reference._vector(probe))


def test_vector_matches_iforest_with_time_of_day() -> None:
    IsolationForestDetector = _iforest_detector_class()
    train = _normal_windows()

    reference = IsolationForestDetector(use_time_of_day=True)
    reference.fit(train)

    vectorizer = WindowVectorizer(use_time_of_day=True)
    vectorizer.fit(train)

    for probe in (_window_at(hour=6), _window_at(hour=0), _window_at(hour=23, minute=59)):
        assert vectorizer.vector(probe) == pytest.approx(reference._vector(probe))


def test_time_of_day_features_match_iforest() -> None:
    IsolationForestDetector = _iforest_detector_class()
    reference = IsolationForestDetector(use_time_of_day=True)
    reference.fit(_normal_windows())

    vectorizer = WindowVectorizer(use_time_of_day=True)
    vectorizer.fit(_normal_windows())

    for probe in (_window_at(hour=0), _window_at(hour=12), _window_at(hour=23, minute=59)):
        assert vectorizer.time_of_day_features(probe) == pytest.approx(
            reference._time_of_day_features(probe)
        )


def test_train_mean_and_std_match_iforest() -> None:
    IsolationForestDetector = _iforest_detector_class()
    train = _normal_windows()

    reference = IsolationForestDetector()
    reference.fit(train)

    vectorizer = WindowVectorizer()
    vectorizer.fit(train)

    assert vectorizer.signals == reference._signals
    assert vectorizer.train_mean == pytest.approx(reference._train_mean)
    assert vectorizer.train_std == pytest.approx(reference._train_std)


def test_missing_signal_fill_matches_iforest() -> None:
    """Absent means "no reading", filled with the *training* mean -- the same
    rule on both sides (`ml/tests/test_iforest_detector.py`'s
    `test_missing_signal_is_filled_with_the_training_mean_not_zero`)."""
    IsolationForestDetector = _iforest_detector_class()
    train = _normal_windows()

    now = datetime.now(UTC)
    partial = MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values={"cpu_percent": [30.0] * 12},  # latency_p95 absent entirely
    )

    reference = IsolationForestDetector()
    reference.fit(train)

    vectorizer = WindowVectorizer()
    vectorizer.fit(train)

    assert vectorizer.vector(partial) == pytest.approx(reference._vector(partial))
