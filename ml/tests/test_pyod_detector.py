"""Tests for ml/detectors/pyod_detector.py.

`pyod_detector` is imported locally inside each test (never at module level)
and guarded by `pytest.importorskip` first -- importing it unconditionally at
module scope would turn a missing `ml` extra into a collection error instead
of a clean skip. Same pattern as `ml/tests/test_harness.py`'s
`test_batch_scoring_produces_identical_results_to_per_window_scoring`.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from core.models.domain import MetricWindow
from ml.detectors import REGISTRY, build

if TYPE_CHECKING:
    # Type-checking only -- never executed, so this cannot turn a missing
    # `pyod` install into an import error at runtime. The real import
    # happens in `_pyod_detector_class`, guarded by `importorskip`.
    from ml.detectors.pyod_detector import PyodDetector

PYOD_DETECTOR_NAMES = ("pyod_ecod", "pyod_copod", "pyod_hbos", "pyod_lof", "pyod_knn")

#: ECOD and COPOD recompute their empirical-CDF order statistics over
#: `X_train` concatenated with WHATEVER is passed to `decision_function`
#: (see `pyod.models.ecod.ECOD.decision_function`'s source) -- so, unlike
#: Isolation Forest and the other three models here, a window's score
#: depends on which other windows are in the same batch call, not just on
#: the window and the training fit. `score_batch` vs `score` is therefore
#: NOT expected to agree for these two; see the dedicated consistency test
#: below instead.
_BATCH_INDEPENDENT = ("pyod_hbos", "pyod_lof", "pyod_knn")
_BATCH_DEPENDENT = ("pyod_ecod", "pyod_copod")


def _pyod_detector_class() -> type[PyodDetector]:
    pytest.importorskip("pyod", reason="requires the `ml` extra")
    from ml.detectors.pyod_detector import PyodDetector as _PyodDetector

    return _PyodDetector


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


def _normal_windows(n: int = 60, seed: int = 7) -> list[MetricWindow]:
    rng = random.Random(seed)
    return [_window(30.0, rng=rng) for _ in range(n)]


@pytest.mark.parametrize("name", PYOD_DETECTOR_NAMES)
def test_registered_under_its_own_name(name: str) -> None:
    PyodDetector = _pyod_detector_class()
    assert name in REGISTRY
    detector = build(name)
    assert isinstance(detector, PyodDetector)
    assert detector.name == name
    assert detector.requires_training is True


@pytest.mark.parametrize("name", PYOD_DETECTOR_NAMES)
def test_builds_fits_and_scores_on_a_tiny_dataset(name: str) -> None:
    PyodDetector = _pyod_detector_class()
    detector = build(name)
    assert isinstance(detector, PyodDetector)
    detector.fit(_normal_windows())
    # 0.5 is the pre-fit class default; fit must replace it.
    assert detector.decision_threshold != 0.5

    score = detector.score(_window(30.0))
    assert isinstance(score, float)

    explanation = detector.explain()
    assert explanation["detector"] == name
    assert explanation["score"] == pytest.approx(score)


@pytest.mark.parametrize("name", PYOD_DETECTOR_NAMES)
def test_score_before_fit_raises(name: str) -> None:
    _pyod_detector_class()
    detector = build(name)
    with pytest.raises(RuntimeError, match=r"fit\(\) must be called"):
        detector.score(_window(30.0))


@pytest.mark.parametrize("name", PYOD_DETECTOR_NAMES)
def test_fit_rejects_too_few_windows(name: str) -> None:
    _pyod_detector_class()
    detector = build(name)
    with pytest.raises(ValueError, match="at least 2 training windows"):
        detector.fit([_window(30.0)])


@pytest.mark.parametrize("name", _BATCH_INDEPENDENT)
def test_score_batch_matches_calling_score_one_at_a_time(name: str) -> None:
    PyodDetector = _pyod_detector_class()
    rng = random.Random(3)
    probe_windows = [_window(cpu, rng=rng) for cpu in (30.0, 97.0, 45.0, 30.0, 85.0)]

    one_at_a_time = build(name)
    assert isinstance(one_at_a_time, PyodDetector)
    one_at_a_time.fit(_normal_windows())
    sequential_scores = [one_at_a_time.score(w) for w in probe_windows]

    batched = build(name)
    assert isinstance(batched, PyodDetector)
    batched.fit(_normal_windows())
    batch_scores = batched.score_batch(probe_windows)

    assert batch_scores == pytest.approx(sequential_scores)


@pytest.mark.parametrize("name", _BATCH_DEPENDENT)
def test_score_batch_is_deterministic_for_a_fixed_batch(name: str) -> None:
    """Not equal to one-at-a-time scoring (see `_BATCH_DEPENDENT` above), but
    calling `score_batch` twice on the identical batch must still agree --
    the harness relies on exactly this to score a whole test slice in one
    call and get reproducible numbers."""
    PyodDetector = _pyod_detector_class()
    rng = random.Random(3)
    probe_windows = [_window(cpu, rng=rng) for cpu in (30.0, 97.0, 45.0, 30.0, 85.0)]

    a = build(name)
    assert isinstance(a, PyodDetector)
    a.fit(_normal_windows())
    b = build(name)
    assert isinstance(b, PyodDetector)
    b.fit(_normal_windows())

    assert a.score_batch(probe_windows) == pytest.approx(b.score_batch(probe_windows))


@pytest.mark.parametrize("name", PYOD_DETECTOR_NAMES)
def test_requires_three_consecutive_breaches_by_default(name: str) -> None:
    _pyod_detector_class()
    detector = build(name)
    detector.fit(_normal_windows())
    rng = random.Random(99)
    for _ in range(10):
        assert detector.is_anomaly(_window(30.0, rng=rng)) is False


@pytest.mark.parametrize("name", PYOD_DETECTOR_NAMES)
def test_reset_clears_an_in_progress_breach_streak(name: str) -> None:
    PyodDetector = _pyod_detector_class()
    detector = build(name, consecutive_breaches_required=1)
    assert isinstance(detector, PyodDetector)
    detector.fit(_normal_windows())
    detector.score_batch([_window(97.0)])  # warm up explain(), unrelated to hysteresis
    detector.reset()
    assert detector.explain()["consecutive_breaches"] == 0
