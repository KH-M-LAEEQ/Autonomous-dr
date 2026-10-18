"""Tests for ml/detectors/lstm.py.

Skipped wholesale when the `ml` extra's torch pin is not installed -- `ml/
detectors/__init__.py` only registers this detector if torch imports.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from core.models.domain import MetricWindow
from ml.detectors import REGISTRY, build

pytest.importorskip("torch", reason="requires the `ml` extra's torch pin")

from ml.detectors.lstm import HISTORY_LENGTH, LSTMDetector  # noqa: E402


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


def _normal_windows(n: int = 40, seed: int = 7) -> list[MetricWindow]:
    rng = random.Random(seed)
    return [_window(30.0, rng=rng) for _ in range(n)]


def _fitted() -> LSTMDetector:
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    detector.fit(_normal_windows())
    return detector


def test_registered_under_lstm_name() -> None:
    assert "lstm" in REGISTRY
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    assert detector.name == "lstm"
    assert detector.requires_training is True


def test_fit_sets_the_iqr_cutoff() -> None:
    detector = _fitted()
    assert detector.decision_threshold != 0.5


def test_fit_rejects_too_few_windows() -> None:
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    with pytest.raises(ValueError, match=f"more than {HISTORY_LENGTH}"):
        detector.fit([_window(30.0) for _ in range(HISTORY_LENGTH)])


def test_score_before_fit_raises() -> None:
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    with pytest.raises(RuntimeError, match="fit\\(\\) must be called"):
        detector.score(_window(30.0))


def test_score_batch_requires_fit_first() -> None:
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    with pytest.raises(RuntimeError, match="fit"):
        detector.score_batch([_window(30.0)])


def test_score_batch_of_empty_list_is_empty() -> None:
    assert _fitted().score_batch([]) == []


def test_first_six_windows_of_a_resource_have_no_history() -> None:
    """Fewer than `HISTORY_LENGTH` predecessors -- scored 0.0, never
    anomalous, whether through sequential `score()` or `score_batch()`."""
    detector = _fitted()
    rng = random.Random(42)
    probes = [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH)]

    sequential = _fitted()
    for window in probes:
        # `score`, not `is_anomaly` -- `is_anomaly` calls `score` itself, and
        # calling both here would score (and append to history) twice.
        assert sequential.score(window) == 0.0

    batched_scores = detector.score_batch(probes)
    assert batched_scores == [0.0] * HISTORY_LENGTH


def test_seventh_window_onward_produces_a_real_forecast_score() -> None:
    detector = _fitted()
    rng = random.Random(42)
    probes = [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH + 2)]
    scores = detector.score_batch(probes)
    assert all(s == 0.0 for s in scores[:HISTORY_LENGTH])
    assert all(s >= 0.0 for s in scores[HISTORY_LENGTH:])


def test_same_seed_gives_the_same_scores_twice() -> None:
    train = _normal_windows()
    a, b = build("lstm"), build("lstm")
    assert isinstance(a, LSTMDetector)
    assert isinstance(b, LSTMDetector)
    a.fit(train)
    b.fit(train)

    rng = random.Random(3)
    probes = [_window(cpu, rng=rng) for cpu in (30.0, 30.0, 30.0, 30.0, 30.0, 30.0, 97.0, 30.0)]
    assert a.score_batch(probes) == pytest.approx(b.score_batch(probes))
    assert a.decision_threshold == pytest.approx(b.decision_threshold)


def test_injected_spike_scores_higher_than_normal() -> None:
    detector = _fitted()
    rng = random.Random(5)
    history = [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH)]

    normal_scores = detector.score_batch([*history, _window(30.0, rng=rng)])
    spike_scores = detector.score_batch([*history, _window(97.0, rng=rng)])

    assert spike_scores[-1] > normal_scores[-1]


def test_requires_three_consecutive_breaches() -> None:
    detector = _fitted()
    rng = random.Random(9)
    history = [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH)]
    for window in history:
        assert detector.is_anomaly(window) is False  # building history, not breaching

    assert detector.is_anomaly(_window(97.0, rng=rng)) is False  # 1st breach
    assert detector.is_anomaly(_window(98.0, rng=rng)) is False  # 2nd breach
    assert detector.is_anomaly(_window(99.0, rng=rng)) is True  # 3rd -- trips


def test_reset_clears_breach_streak_but_not_forecast_history() -> None:
    detector = _fitted()
    rng = random.Random(9)
    for window in [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH)]:
        detector.is_anomaly(window)

    assert detector.is_anomaly(_window(97.0, rng=rng)) is False  # 1st breach
    assert detector.is_anomaly(_window(98.0, rng=rng)) is False  # 2nd breach
    detector.reset()
    assert detector.explain()["consecutive_breaches"] == 0

    # Hysteresis reset, but history is intact -- this is not window 1..6 of
    # the resource again, so a single breach-worthy window does not score 0.0.
    assert detector.score(_window(99.0, rng=rng)) > 0.0


def test_explain_describes_the_last_score_and_never_raises() -> None:
    detector = _fitted()
    assert detector.explain()["detector"] == "lstm"  # before any score() call
    rng = random.Random(1)
    for window in [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH)]:
        detector.score(window)
    detector.score(_window(97.0, rng=rng))
    explanation = detector.explain()
    assert explanation["detector"] == "lstm"
    assert explanation["score"] > 0
    assert explanation["threshold"] == detector.decision_threshold


def test_hysteresis_is_configurable_for_harness_comparisons() -> None:
    detector = build("lstm", consecutive_breaches_required=1)
    assert isinstance(detector, LSTMDetector)
    detector.fit(_normal_windows())
    rng = random.Random(9)
    for window in [_window(30.0, rng=rng) for _ in range(HISTORY_LENGTH)]:
        detector.is_anomaly(window)
    assert detector.is_anomaly(_window(97.0, rng=rng)) is True  # trips on the first breach


def test_fit_accepts_x_val_for_early_stopping() -> None:
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    train = _normal_windows(n=40, seed=1)
    val = _normal_windows(n=20, seed=2)
    detector.fit(train, val)
    assert 0 < detector.epochs_trained <= 20


def test_early_stopping_fires_before_max_epochs_when_val_loss_cannot_improve() -> None:
    """`X_val` drawn from a wildly different distribution than `X`: the
    forecaster converges on train's near-static signal almost immediately,
    after which its val-loss (dominated by the scale mismatch) never sets a
    new best. 3 such epochs in a row must stop training well short of the
    20-epoch cap -- this is the patience-3 branch itself, not just that
    `epochs_trained` lands in `(0, 20]` (`test_fit_accepts_x_val_for_early_
    stopping` passes whether or not that branch ever runs)."""
    detector = build("lstm")
    assert isinstance(detector, LSTMDetector)
    train = _normal_windows(n=50, seed=1)
    val = [_window(850.0, latency=6000.0, rng=random.Random(100 + i)) for i in range(30)]
    detector.fit(train, val)
    assert detector.epochs_trained < 20
