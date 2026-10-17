"""PyOD family -- five more learned detectors benchmarked the same way as
`IsolationForestDetector` (PB-13's last open part).

Reuses `WindowVectorizer` (`ml/detectors/window_features.py`, a standalone
copy of iforest's vectorization logic -- see that module's docstring for why
it is a copy and not an import), the same Tukey IQR fence over training
scores (`ml.detectors.threshold._percentile`/`IQR_MULTIPLIER`), and the same
`CONSECUTIVE_BREACHES_REQUIRED`-consecutive-breach hysteresis. The only thing
that differs between this family and `iforest` is which model turns a vector
into a score.

**Sign convention differs from sklearn, on purpose left alone.** PyOD's
`decision_function` is already "higher = more anomalous" for every model in
the library (unlike sklearn's `IsolationForest.score_samples`, which iforest.py
negates) -- so this adapter does not negate it. Negating a PyOD score would
invert the IQR fence onto the wrong tail.

**Default hyperparameters only, no tuning** (PB-13): each model is
constructed with zero arguments, so whatever PyOD ships as its own default is
what runs here. `contamination` is PyOD's own cutoff knob; like iforest, it is
never consulted -- the IQR fence above is the only cutoff this adapter uses.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pyod.models.copod import COPOD
from pyod.models.ecod import ECOD
from pyod.models.hbos import HBOS
from pyod.models.knn import KNN
from pyod.models.lof import LOF

from core.interfaces.anomaly_detector import AnomalyDetector
from core.models.domain import MetricWindow
from ml.detectors import register
from ml.detectors.threshold import CONSECUTIVE_BREACHES_REQUIRED, IQR_MULTIPLIER, _percentile
from ml.detectors.window_features import WindowVectorizer


class PyodDetector(AnomalyDetector):
    """Generic `AnomalyDetector` adapter around one PyOD model class.

    Not registered itself -- subclasses below set `name` and `_model_cls` and
    are each registered under their own name, the same "one line per
    detector" pattern as `iforest`.
    """

    requires_training = True
    decision_threshold: float = 0.5
    _model_cls: type[Any]

    def __init__(
        self,
        consecutive_breaches_required: int = CONSECUTIVE_BREACHES_REQUIRED,
        use_time_of_day: bool = False,
    ) -> None:
        self._model = self._model_cls()
        self._vectorizer = WindowVectorizer(use_time_of_day=use_time_of_day)
        self._consecutive_breaches = 0
        self._required = consecutive_breaches_required
        self._last_explain: dict[str, Any] = {}
        self._fitted = False

    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        """Fit the PyOD model and the IQR cutoff on normal windows only --
        same contract as `IsolationForestDetector.fit`."""
        if len(X) < 2:
            raise ValueError(f"need at least 2 training windows, got {len(X)}")

        self._vectorizer.fit(X)
        matrix = np.asarray([self._vectorizer.vector(w) for w in X], dtype=float)
        self._model.fit(matrix)
        self._fitted = True

        train_scores = self._model.decision_function(matrix).tolist()
        q1, q3 = _percentile(train_scores, 25), _percentile(train_scores, 75)
        self.decision_threshold = q3 + IQR_MULTIPLIER * (q3 - q1)
        self._consecutive_breaches = 0

    def _build_explain(self, window: MetricWindow, value: float) -> dict[str, Any]:
        deviations = self._vectorizer.deviations(window)
        top = sorted(deviations.items(), key=lambda kv: kv[1], reverse=True)[:3]
        return {
            "score": value,
            "threshold": self.decision_threshold,
            "top_deviating_signals": [
                {"signal": s, "sigmas_from_training_mean": round(d, 3)} for s, d in top
            ],
        }

    def score(self, window: MetricWindow) -> float:
        """Higher is more anomalous -- PyOD's own convention, unlike sklearn's
        `score_samples`, so no negation (contrast `IsolationForestDetector.score`)."""
        if not self._fitted:
            raise RuntimeError("fit() must be called before score()")
        vector = self._vectorizer.vector(window)
        value = float(self._model.decision_function(np.asarray([vector], dtype=float))[0])
        self._last_explain = self._build_explain(window, value)
        return value

    def score_batch(self, windows: list[MetricWindow]) -> list[float]:
        """Vectorised `score()`, mirroring `IsolationForestDetector.score_batch`:
        one `decision_function` call over the whole batch instead of one per
        window, with `is_breach` replaying hysteresis over the result."""
        if not self._fitted:
            raise RuntimeError("fit() must be called before score_batch()")
        if not windows:
            return []
        matrix = np.asarray([self._vectorizer.vector(w) for w in windows], dtype=float)
        values = self._model.decision_function(matrix).tolist()
        self._last_explain = self._build_explain(windows[-1], values[-1])
        return [float(v) for v in values]

    def is_breach(self, score: float) -> bool:
        breach = score > self.decision_threshold
        self._consecutive_breaches = self._consecutive_breaches + 1 if breach else 0
        return self._consecutive_breaches >= self._required

    def is_anomaly(self, window: MetricWindow) -> bool:
        return self.is_breach(self.score(window))

    def explain(self) -> dict[str, Any]:
        return {
            "detector": self.name,
            "consecutive_breaches": self._consecutive_breaches,
            "breaches_required": self._required,
            **self._last_explain,
        }

    def reset(self) -> None:
        self._consecutive_breaches = 0
        self._last_explain = {}


@register("pyod_ecod")
class ECODDetector(PyodDetector):
    name = "pyod_ecod"
    _model_cls = ECOD


@register("pyod_copod")
class COPODDetector(PyodDetector):
    name = "pyod_copod"
    _model_cls = COPOD


@register("pyod_hbos")
class HBOSDetector(PyodDetector):
    name = "pyod_hbos"
    _model_cls = HBOS


@register("pyod_lof")
class LOFDetector(PyodDetector):
    name = "pyod_lof"
    _model_cls = LOF


@register("pyod_knn")
class KNNDetector(PyodDetector):
    name = "pyod_knn"
    _model_cls = KNN
