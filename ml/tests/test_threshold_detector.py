"""Tests for ml/detectors/threshold.py -- the permanent Week 4 baseline."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from core.models.domain import MetricWindow
from ml.detectors import build
from ml.detectors.threshold import CONSECUTIVE_BREACHES_REQUIRED, ThresholdDetector

# Roughly the simulator's web_service baseline, with the point of the whole
# exercise built in: cpu is tens, net_in_bytes is millions.
_CPU_MEAN, _CPU_STD = 30.0, 8.0
_NET_MEAN, _NET_STD = 5_000_000.0, 1_000_000.0
_LAT_MEAN, _LAT_STD = 120.0, 20.0


def _window(
    cpu: float = _CPU_MEAN,
    net_in: float = _NET_MEAN,
    latency: float = _LAT_MEAN,
    rng: random.Random | None = None,
    extra: dict[str, list[float]] | None = None,
) -> MetricWindow:
    r = rng or random.Random(0)
    now = datetime.now(UTC)
    values: dict[str, list[float]] = {
        "cpu_percent": [cpu + r.gauss(0, 1.0) for _ in range(12)],
        "net_in_bytes": [net_in + r.gauss(0, 50_000.0) for _ in range(12)],
        "latency_p95": [latency + r.gauss(0, 4.0) for _ in range(12)],
    }
    if extra:
        values.update(extra)
    return MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values=values,
    )


def _training(
    n: int = 300, seed: int = 1, extra: dict[str, list[float]] | None = None
) -> list[MetricWindow]:
    """Normal windows with realistic per-signal noise."""
    rng = random.Random(seed)
    return [
        _window(
            cpu=rng.gauss(_CPU_MEAN, _CPU_STD),
            net_in=rng.gauss(_NET_MEAN, _NET_STD),
            latency=rng.gauss(_LAT_MEAN, _LAT_STD),
            rng=rng,
            extra=extra,
        )
        for _ in range(n)
    ]


def _fitted(seed: int = 1) -> ThresholdDetector:
    detector = build("threshold")
    assert isinstance(detector, ThresholdDetector)
    detector.fit(_training(seed=seed))
    return detector


def _trips(
    detector: ThresholdDetector, factory: Callable[[], MetricWindow], n: int = 4
) -> bool:
    """Feed n consecutive windows; True if the detector ever fires."""
    return any(detector.is_anomaly(factory()) for _ in range(n))


def test_registered_under_threshold_name() -> None:
    detector = build("threshold")
    assert isinstance(detector, ThresholdDetector)
    assert detector.name == "threshold"


def test_fit_rejects_empty_training_set() -> None:
    detector = build("threshold")
    with pytest.raises(ValueError, match="at least 1 training window"):
        detector.fit([])


def test_fit_rejects_windows_with_no_detector_signals() -> None:
    now = datetime.now(UTC)
    # uptime_seconds is canonical but excluded from detector features, so a
    # window carrying only it has nothing to score.
    window = MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values={"uptime_seconds": [100.0] * 12},
    )
    detector = build("threshold")
    with pytest.raises(ValueError, match="no detector signals"):
        detector.fit([window])


# -- the scale-domination fix (STEP 3) -------------------------------------


def test_a_cpu_spike_fires() -> None:
    """The regression this fix exists for: cpu is tens, net_in is millions, and
    before per-signal scaling a 67-point cpu spike could never cross a fence
    set by byte-rate noise."""
    detector = _fitted()
    assert _trips(detector, lambda: _window(cpu=97.0))


def test_a_byte_rate_spike_also_fires() -> None:
    """Scaling must not simply invert the old bias -- the large-magnitude
    signal still has to work."""
    detector = _fitted()
    assert _trips(detector, lambda: _window(net_in=_NET_MEAN * 5))


def test_cpu_and_byte_rate_spikes_are_comparably_scored() -> None:
    """Both are ~8 sigma events, so their residuals should be the same order of
    magnitude. Before the fix they differed by ~10^5."""
    detector = _fitted()
    cpu_residual = detector.score(_window(cpu=_CPU_MEAN + 8 * _CPU_STD))
    net_residual = detector.score(_window(net_in=_NET_MEAN + 8 * _NET_STD))
    assert 0.2 < cpu_residual / net_residual < 5.0


def test_normal_readings_rarely_fire() -> None:
    """Over 200 fresh normal windows the 3-breach rule should essentially never
    trip. 'Rarely', not 'never' -- it is a statistical fence."""
    detector = _fitted()
    rng = random.Random(99)
    fired = sum(
        detector.is_anomaly(
            _window(
                cpu=rng.gauss(_CPU_MEAN, _CPU_STD),
                net_in=rng.gauss(_NET_MEAN, _NET_STD),
                latency=rng.gauss(_LAT_MEAN, _LAT_STD),
                rng=rng,
            )
        )
        for _ in range(200)
    )
    assert fired <= 4, f"{fired}/200 normal windows fired"


def test_a_zero_spread_signal_does_not_crash() -> None:
    """health_check_pass is 1.0 in every normal window, so its IQR is 0 and a
    naive divide would blow up. It falls back to its own magnitude."""
    constant = {"health_check_pass": [1.0] * 12}
    detector = build("threshold")
    assert isinstance(detector, ThresholdDetector)
    detector.fit(_training(extra=constant))

    assert detector._spread["health_check_pass"] == 1.0
    # Scoring stays finite, both for a normal window and a failed health check.
    assert detector.score(_window(extra=constant)) >= 0.0
    dropped = detector.score(_window(extra={"health_check_pass": [0.0] * 12}))
    assert dropped > 0.0


def test_a_zero_valued_zero_spread_signal_does_not_crash() -> None:
    """Worse case: the signal is constant AND zero, so magnitude is 0 too."""
    detector = build("threshold")
    assert isinstance(detector, ThresholdDetector)
    detector.fit(_training(extra={"throttle_count": [0.0] * 12}))
    assert detector._spread["throttle_count"] == 1.0
    assert detector.score(_window(extra={"throttle_count": [3.0] * 12})) > 0.0


# -- hysteresis ------------------------------------------------------------


def test_requires_three_consecutive_breaches() -> None:
    detector = _fitted()
    assert detector.is_anomaly(_window(cpu=97.0)) is False  # 1st breach
    assert detector.is_anomaly(_window(cpu=98.0)) is False  # 2nd breach
    assert detector.is_anomaly(_window(cpu=99.0)) is True  # 3rd -- trips


def test_a_normal_reading_resets_the_breach_counter() -> None:
    detector = _fitted()
    assert detector.is_anomaly(_window(cpu=97.0)) is False
    assert detector.is_anomaly(_window(cpu=98.0)) is False
    assert detector.is_anomaly(_window()) is False  # back to normal -- resets
    assert detector.is_anomaly(_window(cpu=97.0)) is False  # count is back to 1
    assert detector.is_anomaly(_window(cpu=98.0)) is False


def test_consecutive_breaches_required_is_three() -> None:
    assert CONSECUTIVE_BREACHES_REQUIRED == 3


# -- signal selection ------------------------------------------------------


def test_uptime_seconds_is_ignored_even_when_present() -> None:
    """It is a monotonic counter; a detector fitted on it learns a ramp. A huge
    jump in uptime alone must not score."""
    detector = _fitted()
    before = detector.score(_window())
    after = detector.score(_window(extra={"uptime_seconds": [9_999_999.0] * 12}))
    assert after == pytest.approx(before)


def test_absent_signals_are_skipped_not_imputed() -> None:
    """A window missing net_in_bytes entirely is scored on what it has, and
    must not be penalised as though net_in had dropped to zero."""
    detector = _fitted()
    now = datetime.now(UTC)
    partial = MetricWindow(
        resource_id="r1",
        tenant_id="t1",
        start=now - timedelta(seconds=110),
        end=now,
        step_seconds=10,
        values={"cpu_percent": [_CPU_MEAN] * 12},
    )
    assert detector.score(partial) < detector.decision_threshold
    assert detector.explain()["signals_scored"] == 1


# -- the BEFORE detector ---------------------------------------------------


def test_unscaled_variant_is_registered_for_the_before_row() -> None:
    from ml.detectors.threshold import UnscaledThresholdDetector

    detector = build("threshold_unscaled")
    assert isinstance(detector, UnscaledThresholdDetector)
    assert detector.name == "threshold_unscaled"


def test_unscaled_variant_cannot_be_selected_by_config() -> None:
    """It exists to document a regression, not to be run in production."""
    import typing

    from core.config import Settings

    allowed = typing.get_args(Settings.model_fields["detector"].annotation)
    assert "threshold_unscaled" not in allowed
    assert "threshold" in allowed


def test_unscaled_variant_reproduces_the_scale_domination_bug() -> None:
    """A cpu spike must be invisible to it: that is the whole finding. Its fence
    is set by byte-rate noise, orders of magnitude above anything cpu can
    reach."""
    detector = build("threshold_unscaled")
    assert isinstance(detector, ThresholdDetector)
    detector.fit(_training())

    assert detector.decision_threshold > 100_000, "fence should be byte-rate scale"
    assert not _trips(detector, lambda: _window(cpu=97.0), n=10)
    # And the fixed detector does catch the same spike.
    assert _trips(_fitted(), lambda: _window(cpu=97.0))


def test_explain_reports_the_offending_signal_and_its_scale() -> None:
    detector = _fitted()
    detector.is_anomaly(_window(cpu=97.0))
    explanation = detector.explain()
    assert explanation["detector"] == "threshold"
    assert explanation["signal"] == "cpu_percent"
    assert explanation["consecutive_breaches"] == 1
    assert explanation["training_spread"] > 0
    assert "training_median" in explanation
