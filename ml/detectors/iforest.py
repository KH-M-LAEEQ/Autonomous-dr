"""IsolationForestDetector -- the first learned detector, benchmarked against
the Week 4 threshold baseline.

Unsupervised novelty detection: `fit` is given **normal windows only** and
learns what normal looks like. Anything far from that in feature space scores
high. It never sees a labelled fault during training, which is the point --
labels are for scoring, not for fitting.

Two deliberate choices that make the comparison against `ThresholdDetector`
mean something:

**Same thresholding rule, different scorer.** The cutoff is Tukey's IQR fence
(`Q3 + 1.5*(Q3-Q1)`) over *training* scores, exactly as the threshold baseline
does, and `docs/formulas.md` §2 records IQR as the project default. So the only
variable between the two detectors is how the score is computed, not how the
cutoff is drawn.

**Same hysteresis.** A detection needs
`CONSECUTIVE_BREACHES_REQUIRED` consecutive breaches, matching the baseline.
Otherwise a comparison measures debouncing rather than detection.

Scale is left alone on purpose: Isolation Forest splits one feature at a time
at a random point inside that feature's own observed range, so a signal in
bytes/s and a signal in percent do not need standardising to coexist.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from core.interfaces.anomaly_detector import AnomalyDetector
from core.models.domain import MetricWindow
from core.signals import DETECTOR_SIGNALS
from ml.detectors import register
from ml.detectors.threshold import CONSECUTIVE_BREACHES_REQUIRED, IQR_MULTIPLIER, _percentile

# Per signal: mean, population std, and the most recent reading. Three summary
# features beat the raw 12-sample series -- the series length can vary at the
# edges of a collection gap, and a fixed-width vector cannot.
_FEATURES_PER_SIGNAL = ("mean", "std", "last")


@register("iforest")
class IsolationForestDetector(AnomalyDetector):
    """Isolation Forest over per-signal summary features of one `MetricWindow`.

    One instance per monitor node, per the `AnomalyDetector` contract --
    `_consecutive_breaches` and the last-score state behind `explain` are
    per-instance and a shared instance would corrupt both across nodes.
    """

    name = "iforest"
    requires_training = True
    # Declared here so the attribute exists before `fit` under either version
    # of the interface: the post-freeze `AnomalyDetector` defines it on the
    # base class, the pre-freeze one on this branch does not. `fit` overwrites
    # it with the IQR fence; this default is never used for a real decision.
    decision_threshold: float = 0.5

    def __init__(
        self,
        n_estimators: int = 100,
        random_state: int = 0,
        consecutive_breaches_required: int = CONSECUTIVE_BREACHES_REQUIRED,
    ) -> None:
        self._forest = IsolationForest(
            n_estimators=n_estimators,
            # Unused on this code path: the cutoff comes from the IQR fence
            # below, not from sklearn's own offset_, so contamination never
            # moves a decision here.
            contamination="auto",
            random_state=random_state,
        )
        self._signals: tuple[str, ...] = ()
        self._train_mean: dict[str, float] = {}
        self._train_std: dict[str, float] = {}
        self._consecutive_breaches = 0
        self._required = consecutive_breaches_required
        self._last_explain: dict[str, Any] = {}
        self._fitted = False

    # -- features ---------------------------------------------------------

    def _vector(self, window: MetricWindow) -> list[float]:
        """Flattened per-signal summary, in the signal order fixed at `fit`.

        A signal missing from the window is filled with its *training mean*,
        never 0.0 -- absent means "no reading", and zero-filling would hand the
        forest a hard outlier that the data never contained (both metric docs
        state this rule explicitly).
        """
        vector: list[float] = []
        for signal in self._signals:
            series = window.values.get(signal) or []
            if series:
                mean = sum(series) / len(series)
                variance = sum((v - mean) ** 2 for v in series) / len(series)
                vector.extend([mean, math.sqrt(variance), series[-1]])
            else:
                fill = self._train_mean.get(signal, 0.0)
                vector.extend([fill, self._train_std.get(signal, 0.0), fill])
        return vector

    # -- AnomalyDetector --------------------------------------------------

    def fit(self, X: list[MetricWindow]) -> None:
        """Fit the forest and the IQR cutoff on normal windows only.

        `X` must contain no known faults -- this is a novelty detector, and a
        fault in the training set teaches it that the fault is normal. The
        caller owns the chronological split (ADR-0008 70/15/15 via
        `ml.harness.evaluate.time_based_split`); this never splits `X` itself.
        """
        if len(X) < 2:
            raise ValueError(f"need at least 2 training windows, got {len(X)}")

        # Signal order is frozen here and every later vector follows it.
        # Restricted to DETECTOR_SIGNALS: the 20 canonical signals minus
        # `uptime_seconds`. Reserve signals are collected but consumed by
        # nothing (docs/metric-schema.md), and a monotonic counter would teach
        # the forest that the passage of time is anomalous.
        present: list[str] = []
        for window in X:
            for signal in DETECTOR_SIGNALS:
                if signal not in present and window.values.get(signal):
                    present.append(signal)
        if not present:
            raise ValueError("training windows carry no detector signals")
        self._signals = tuple(present)

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for window in X:
            for signal in self._signals:
                for value in window.values.get(signal) or []:
                    sums[signal] = sums.get(signal, 0.0) + value
                    counts[signal] = counts.get(signal, 0) + 1
        self._train_mean = {s: sums[s] / counts[s] for s in sums}
        self._train_std = {
            s: math.sqrt(
                sum(
                    (v - self._train_mean[s]) ** 2
                    for w in X
                    for v in w.values.get(s, [])
                )
                / counts[s]
            )
            for s in sums
        }

        matrix = np.asarray([self._vector(w) for w in X], dtype=float)
        self._forest.fit(matrix)
        self._fitted = True

        train_scores = (-self._forest.score_samples(matrix)).tolist()
        q1, q3 = _percentile(train_scores, 25), _percentile(train_scores, 75)
        self.decision_threshold = q3 + IQR_MULTIPLIER * (q3 - q1)
        self._consecutive_breaches = 0

    def score(self, window: MetricWindow) -> float:
        """Higher is more anomalous. sklearn's `score_samples` is the opposite
        way round (higher = more normal), hence the negation."""
        if not self._fitted:
            raise RuntimeError("fit() must be called before score()")
        vector = self._vector(window)
        value = float(-self._forest.score_samples(np.asarray([vector], dtype=float))[0])

        deviations = {
            signal: abs(window.values[signal][-1] - self._train_mean.get(signal, 0.0))
            / (self._train_std.get(signal) or 1.0)
            for signal in self._signals
            if window.values.get(signal)
        }
        top = sorted(deviations.items(), key=lambda kv: kv[1], reverse=True)[:3]
        self._last_explain = {
            "score": value,
            "threshold": self.decision_threshold,
            "top_deviating_signals": [
                {"signal": s, "sigmas_from_training_mean": round(d, 3)} for s, d in top
            ],
        }
        return value

    def is_anomaly(self, window: MetricWindow) -> bool:
        """Overrides the default for hysteresis, and because the pre-freeze
        `AnomalyDetector.is_anomaly` on this branch still routes through a
        `ThresholdStrategy` this detector does not use. Explicit here, so it
        behaves identically under the old and the post-freeze contract."""
        breach = self.score(window) > self.decision_threshold
        self._consecutive_breaches = self._consecutive_breaches + 1 if breach else 0
        return self._consecutive_breaches >= self._required

    def explain(self) -> dict[str, Any]:
        """Describes the last `score` call. Never raises.

        Isolation Forest has no native per-feature attribution, so the
        explanation reports which signals sat furthest from their training mean
        at that moment -- honest about being a correlate of the score, not a
        decomposition of it.
        """
        return {
            "detector": self.name,
            "consecutive_breaches": self._consecutive_breaches,
            "breaches_required": self._required,
            **self._last_explain,
        }
