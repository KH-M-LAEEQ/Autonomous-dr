"""FROZEN INTERFACE 2 of 5 -- AnomalyDetector.

Implemented by: ThresholdDetector (W4, permanent baseline -- never delete),
IsolationForestDetector (W10), PyOD family (W10), LSTMDetector (W11),
EnsembleDetector (W11), GNNDetector (W14).

Every implementation is scored by the same harness on the same time-based split.
That comparability is worth more than any individual model.
"""

from abc import ABC, abstractmethod
from typing import Any

from core.models.domain import MetricWindow


class AnomalyDetector(ABC):
    """Turns a window of telemetry into a scalar anomaly score.

    Contract:
      * `score` is higher = more anomalous, and comparable across calls for the
        same instance (not across detectors -- that is what the harness normalises).
      * `fit` may be a no-op for rule-based detectors.
      * `explain` describes the LAST call to `score` and must never raise.
    """

    name: str
    requires_training: bool = True

    @abstractmethod
    def fit(self, X: list[MetricWindow]) -> None:
        """Train on normal-behaviour windows. No-op for rule-based detectors."""
        ...

    @abstractmethod
    def score(self, window: MetricWindow) -> float:
        """Anomaly score for one window. Higher is more anomalous."""
        ...

    @abstractmethod
    def explain(self) -> dict[str, Any]:
        """Why the last score came out that way: contributing signals, threshold,
        residual magnitude. Feeds the dashboard and the RAG prompt. Never raises.
        """
        ...

    def is_anomaly(self, window: MetricWindow) -> bool:
        """Convenience wrapper. Override if your detector has internal hysteresis
        (the threshold rule does: 3 consecutive breaches)."""
        return self.score(window) >= self.decision_threshold

    decision_threshold: float = 0.5
