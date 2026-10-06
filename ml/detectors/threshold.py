"""ThresholdDetector -- Week 4's `AnomalyDetector` baseline.

Deliberately simple: the residual is the largest per-signal deviation from a
training-time baseline mean, and a detection requires 3 CONSECUTIVE breaches
of the fitted `threshold_strategy` cutoff, never a single spike. This is the
permanent baseline every later detector (IForest, LSTM, ensemble, GNN) gets
benchmarked against in the Week 10 harness -- never delete it.
"""

from __future__ import annotations

from typing import Any

from core.interfaces.anomaly_detector import AnomalyDetector, ThresholdStrategy
from core.models.domain import MetricWindow
from ml.detectors import register

CONSECUTIVE_BREACHES_REQUIRED = 3


def _last_values(window: MetricWindow) -> dict[str, float]:
    return {signal: series[-1] for signal, series in window.values.items() if series}


@register("threshold")
class ThresholdDetector(AnomalyDetector):
    """3-consecutive-breach rule over the max per-signal deviation from a
    fitted training baseline.

    One instance per monitor node, per the `AnomalyDetector` contract --
    `_consecutive_breaches` is per-instance state that a shared instance
    would corrupt across nodes.
    """

    name = "threshold"
    requires_training = True

    def __init__(self, threshold_strategy: ThresholdStrategy | None = None) -> None:
        super().__init__(threshold_strategy)
        self._baseline: dict[str, float] = {}
        self._consecutive_breaches = 0
        self._last_explain: dict[str, Any] = {}

    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        """Baseline mean per signal over every training window's full series.
        `X_val` is unused -- this detector has no held-out-set use, per the
        `AnomalyDetector.fit` contract."""
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for window in X:
            for signal, series in window.values.items():
                for value in series:
                    sums[signal] = sums.get(signal, 0.0) + value
                    counts[signal] = counts.get(signal, 0) + 1
        self._baseline = {signal: sums[signal] / counts[signal] for signal in sums}

        residuals = [self._residual(window) for window in X]
        self.threshold_strategy.fit(residuals)
        self._consecutive_breaches = 0

    def _residual(self, window: MetricWindow) -> float:
        """Max absolute deviation of the window's latest reading from the
        fitted per-signal baseline -- a spike in ANY one signal is what this
        baseline rule exists to catch, not just a drift in the average."""
        latest = _last_values(window)
        if not latest:
            self._last_explain = {}
            return 0.0
        deviations = {
            signal: abs(value - self._baseline.get(signal, value))
            for signal, value in latest.items()
        }
        signal, residual = max(deviations.items(), key=lambda item: item[1])
        self._last_explain = {
            "signal": signal,
            "residual": residual,
            "latest_value": latest[signal],
        }
        return residual

    def score(self, window: MetricWindow) -> float:
        return self._residual(window)

    def is_anomaly(self, window: MetricWindow) -> bool:
        """Overrides the default to add hysteresis: 3 consecutive breaches,
        not one spike, is a detection (see module docstring)."""
        breach = self.threshold_strategy.is_anomalous(self.score(window))
        self._consecutive_breaches = self._consecutive_breaches + 1 if breach else 0
        return self._consecutive_breaches >= CONSECUTIVE_BREACHES_REQUIRED

    def explain(self) -> dict[str, Any]:
        return {
            "detector": self.name,
            "consecutive_breaches": self._consecutive_breaches,
            **self._last_explain,
        }
