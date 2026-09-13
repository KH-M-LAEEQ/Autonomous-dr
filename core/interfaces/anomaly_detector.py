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


class ThresholdStrategy(ABC):
    """Turns a residual into an anomalous/normal call. Pluggable so the Week 10
    harness can swap strategies on the same detector output and produce a
    false-positive-rate comparison table (ADR-0009, docs/formulas.md §2).

    Contract:
      * `fit` is calibrated on TRAINING residuals only -- never val or test,
        or the comparison table leaks information across the split.
      * `is_anomalous` must never raise; call `fit` before it.
    """

    @abstractmethod
    def fit(self, train_residuals: list[float]) -> None:
        """Calibrate the cutoff from training residuals only."""
        ...

    @abstractmethod
    def is_anomalous(self, residual: float) -> bool:
        """Whether `residual` crosses the calibrated cutoff."""
        ...


class AnomalyDetector(ABC):
    """Turns a window of telemetry into a scalar anomaly score.

    Contract:
      * `score` is higher = more anomalous, and comparable across calls for the
        same instance (not across detectors -- that is what the harness normalises).
      * `fit` may be a no-op for rule-based detectors.
      * `explain` describes the LAST call to `score` and must never raise.
      * Each monitor node owns its own detector instance, never a shared one --
        `explain` reads state left behind by the last `score` call, so a shared
        instance lets one node's `explain` describe a different node's score.
    """

    name: str
    requires_training: bool = True

    def __init__(self, threshold_strategy: ThresholdStrategy | None = None) -> None:
        from core.threshold_strategies import IQRThreshold

        self.threshold_strategy: ThresholdStrategy = threshold_strategy or IQRThreshold()

    @abstractmethod
    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        """Train on normal-behaviour windows. No-op for rule-based detectors.

        `X` and `X_val` are the ADR-0008 70/15/15 chronological split, computed
        once by the harness and passed in -- detectors must never carve their
        own split out of `X`, or per-detector splits make the harness comparison
        invalid. `X_val` is required by detectors that need a held-out set
        during fitting (the W11 LSTM early-stops on it, patience=5) and is
        `None` for detectors with no such use (e.g. the threshold baseline).

        Implementations that use `threshold_strategy` must call
        `self.threshold_strategy.fit(...)` here on TRAINING residuals only,
        never on `X_val` or test data.
        """
        ...

    @abstractmethod
    def score(self, window: MetricWindow) -> float:
        """Anomaly score for one window. Higher is more anomalous.

        For per-node detectors (e.g. the W14 GNN scoring a graph of nodes at
        once), return the max score across nodes here; put the per-node
        breakdown in `explain()` instead, not in this return value.
        """
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
        return self.threshold_strategy.is_anomalous(self.score(window))
