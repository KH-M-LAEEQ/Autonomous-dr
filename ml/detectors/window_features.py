"""Shared per-window feature extraction for Week 10's learned detectors.

A standalone copy of `IsolationForestDetector`'s vectorization logic
(`ml/detectors/iforest.py`), not an import from it -- `iforest.py` has tests
that poke its private `_vector`/`_train_mean`/`_time_of_day_features`
attributes directly (`ml/tests/test_iforest_detector.py`), so refactoring it
to compose this class would mean either breaking that surface or re-exposing
it through thin wrappers for no behavioural gain. Copied instead of
reinvented: this is the exact same mean/std/last-per-signal vector, the exact
same training-mean fill rule for an absent signal, and the exact same
optional time-of-day features, so a model built on top of it (the PyOD
family, `ml/detectors/pyod_detector.py`) sees precisely what Isolation Forest
sees. `iforest.py` is unmodified by this module's existence.
"""

from __future__ import annotations

import math

from core.models.domain import MetricWindow
from core.signals import DETECTOR_SIGNALS

_SECONDS_PER_DAY = 86_400.0


class WindowVectorizer:
    """Flattens one `MetricWindow` into a fixed-width feature vector: per
    signal mean/std/last, in the signal order fixed at `fit`, optionally
    followed by sin/cos-of-hour-of-day."""

    def __init__(self, use_time_of_day: bool = False) -> None:
        self.signals: tuple[str, ...] = ()
        self.train_mean: dict[str, float] = {}
        self.train_std: dict[str, float] = {}
        self.use_time_of_day = use_time_of_day

    def fit(self, X: list[MetricWindow]) -> None:
        """Freezes signal order and per-signal training mean/std from normal
        windows only. Raises if none of `DETECTOR_SIGNALS` appear in `X`."""
        present: list[str] = []
        for window in X:
            for signal in DETECTOR_SIGNALS:
                if signal not in present and window.values.get(signal):
                    present.append(signal)
        if not present:
            raise ValueError("training windows carry no detector signals")
        self.signals = tuple(present)

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for window in X:
            for signal in self.signals:
                for value in window.values.get(signal) or []:
                    sums[signal] = sums.get(signal, 0.0) + value
                    counts[signal] = counts.get(signal, 0) + 1
        self.train_mean = {s: sums[s] / counts[s] for s in sums}
        self.train_std = {
            s: math.sqrt(
                sum((v - self.train_mean[s]) ** 2 for w in X for v in w.values.get(s, []))
                / counts[s]
            )
            for s in sums
        }

    def time_of_day_features(self, window: MetricWindow) -> list[float]:
        seconds_of_day = window.end.hour * 3600 + window.end.minute * 60 + window.end.second
        angle = 2 * math.pi * seconds_of_day / _SECONDS_PER_DAY
        return [math.sin(angle), math.cos(angle)]

    def vector(self, window: MetricWindow) -> list[float]:
        """A signal missing from the window is filled with its *training
        mean*, never 0.0 -- absent means "no reading", not an outlier."""
        vector: list[float] = []
        for signal in self.signals:
            series = window.values.get(signal) or []
            if series:
                mean = sum(series) / len(series)
                variance = sum((v - mean) ** 2 for v in series) / len(series)
                vector.extend([mean, math.sqrt(variance), series[-1]])
            else:
                fill = self.train_mean.get(signal, 0.0)
                vector.extend([fill, self.train_std.get(signal, 0.0), fill])
        if self.use_time_of_day:
            vector.extend(self.time_of_day_features(window))
        return vector

    def deviations(self, window: MetricWindow) -> dict[str, float]:
        """How many training standard deviations the window's latest sample
        sits from the training mean, per signal present in the window --
        feeds `explain()`'s top-3 deviating-signal readout."""
        return {
            signal: abs(window.values[signal][-1] - self.train_mean.get(signal, 0.0))
            / (self.train_std.get(signal) or 1.0)
            for signal in self.signals
            if window.values.get(signal)
        }
