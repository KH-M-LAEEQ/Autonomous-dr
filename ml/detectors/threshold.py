"""ThresholdDetector -- Week 4's `AnomalyDetector` baseline.

The rule: scale each signal by its own normal spread, take the largest scaled
deviation as the residual, and require 3 CONSECUTIVE breaches of a fitted IQR
fence before calling it a detection. This is the permanent baseline every later
detector (IForest, LSTM, ensemble, GNN) is benchmarked against in the Week 10
harness -- never delete it.

**Why the per-signal scaling exists.** The first version took the largest
*absolute* deviation from a per-signal mean, across signals whose units span six
orders of magnitude. `net_in_bytes` sits in the millions, so its ordinary noise
set the fence at ~4.1e6 and nothing else could ever reach it: a `cpu_percent`
spike of 67 points scored 67 against a fence of four million. The detector fired
zero times on the whole v3 practice dataset -- silent, not inaccurate (see
`docs/results/practice-run.md`). Dividing each signal by its own
interquartile range puts every signal on a comparable "how unusual is this for
*this* signal" scale, which is the only way a max() across them means anything.

Median and IQR rather than mean and standard deviation, because both are
robust: a single contaminated training window cannot drag the centre or inflate
the spread the way a mean and an sd would.

A zero-spread signal (`health_check_pass` is 1.0 in every normal window) would
divide by zero. It falls back to its own magnitude, so a 1 -> 0 drop scores 1.0
-- one unit of its own scale -- instead of infinity.

The cutoff is Tukey's IQR fence, `Q3 + 1.5*(Q3-Q1)`, over *training* residuals,
per `docs/formulas.md` section 2. That section states the fence two-sided
(`r < Q1 - 1.5*IQR or r > Q3 + 1.5*IQR`) because it is written for the Week 11
LSTM's signed residuals `r = x - x_hat`. This detector's residual is a
*magnitude*: it is non-negative by construction, so the lower arm sits below
zero and can never fire. Only the upper arm is applied, and that is the same
rule, not a weaker one.
"""

from __future__ import annotations

import math
from typing import Any

from core.interfaces.anomaly_detector import AnomalyDetector
from core.models.domain import MetricWindow
from core.signals import DETECTOR_SIGNALS
from ml.detectors import register

CONSECUTIVE_BREACHES_REQUIRED = 3
IQR_MULTIPLIER = 1.5

#: v2 scaling floor (`docs/notes/scale-floor-v2.md`), opt-in via
#: `use_scale_floor` -- off by default, so `threshold`/`lstm` are exactly v1.
#: `spread = max(spread_v1, floor)` for bounded signals only: 1% of the
#: documented range in `docs/metric-schema.md`. Every other signal is absent
#: from this dict and gets no floor.
SCALE_FLOORS: dict[str, float] = {
    "cpu_percent": 1.0,
    "memory_percent": 1.0,
    "disk_used_percent": 1.0,
    "error_rate_5xx": 0.01,
    "error_rate_4xx": 0.01,
}


def _percentile(data: list[float], q: float) -> float:
    """Linear-interpolation percentile, 0 <= q <= 100."""
    ordered = sorted(data)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    rank = (q / 100) * (n - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return ordered[int(rank)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def _last_values(window: MetricWindow) -> dict[str, float]:
    """Latest reading per *detector* signal that the window actually carries.

    Absent signals are skipped, never imputed: a missing key is null, and null
    is not zero (`core/signals.py`). `uptime_seconds` is excluded upstream by
    `DETECTOR_SIGNALS` because it is a monotonic counter.
    """
    latest: dict[str, float] = {}
    for signal in DETECTOR_SIGNALS:
        series = window.values.get(signal)
        if series:
            latest[signal] = series[-1]
    return latest


@register("threshold")
class ThresholdDetector(AnomalyDetector):
    """3-consecutive-breach rule over the largest spread-scaled per-signal
    deviation from a fitted training baseline.

    One instance per monitor node, per the `AnomalyDetector` contract --
    `_consecutive_breaches` is per-instance state that a shared instance
    would corrupt across nodes.
    """

    name = "threshold"
    requires_training = True
    # Declared here so the attribute exists before `fit` under either version
    # of the interface: the post-freeze `AnomalyDetector` defines it on the
    # base class, the pre-freeze one on this branch does not. `fit` overwrites
    # it with the IQR fence; this default is never used for a real decision.
    decision_threshold: float = 0.5

    def __init__(self, use_scale_floor: bool = False) -> None:
        self._median: dict[str, float] = {}
        self._spread: dict[str, float] = {}
        self._consecutive_breaches = 0
        self._last_explain: dict[str, Any] = {}
        #: Opt-in, off by default -- see `SCALE_FLOORS` above and
        #: `docs/notes/scale-floor-v2.md`. `threshold_v2` turns this on.
        self._use_scale_floor = use_scale_floor

    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        """Per-signal median and IQR over every training window's full series,
        then the IQR fence over the resulting training residuals."""
        if not X:
            raise ValueError("need at least 1 training window")

        samples: dict[str, list[float]] = {}
        for window in X:
            for signal in DETECTOR_SIGNALS:
                series = window.values.get(signal)
                if series:
                    samples.setdefault(signal, []).extend(series)
        if not samples:
            raise ValueError("training windows carry no detector signals")

        self._median = {s: _percentile(v, 50) for s, v in samples.items()}
        self._spread = {}
        for signal, values in samples.items():
            iqr = _percentile(values, 75) - _percentile(values, 25)
            if iqr > 0:
                spread = iqr
            else:
                # Constant in training. Fall back to its own magnitude so a
                # departure scores ~1.0 rather than dividing by zero.
                magnitude = abs(self._median[signal])
                spread = magnitude if magnitude > 0 else 1.0
            if self._use_scale_floor and signal in SCALE_FLOORS:
                spread = max(spread, SCALE_FLOORS[signal])
            self._spread[signal] = spread

        residuals = [self._residual(window) for window in X]
        q1, q3 = _percentile(residuals, 25), _percentile(residuals, 75)
        self.decision_threshold = q3 + IQR_MULTIPLIER * (q3 - q1)
        self._consecutive_breaches = 0

    def _residual(self, window: MetricWindow) -> float:
        """Largest spread-scaled deviation of the window's latest reading from
        the fitted per-signal median. A spike in ANY one signal is what this
        baseline rule exists to catch, and scaling is what makes "any" fair."""
        latest = _last_values(window)
        deviations = {
            signal: abs(value - self._median[signal]) / self._spread[signal]
            for signal, value in latest.items()
            if signal in self._median
        }
        if not deviations:
            self._last_explain = {}
            return 0.0

        signal, residual = max(deviations.items(), key=lambda item: item[1])
        self._last_explain = {
            "signal": signal,
            "residual": residual,
            "latest_value": latest[signal],
            "training_median": self._median[signal],
            "training_spread": self._spread[signal],
            "signals_scored": len(deviations),
        }
        return residual

    def score(self, window: MetricWindow) -> float:
        return self._residual(window)

    def is_anomaly(self, window: MetricWindow) -> bool:
        """Overrides the default to add hysteresis: 3 consecutive breaches,
        not one spike, is a detection (see module docstring)."""
        breach = self.score(window) > self.decision_threshold
        self._consecutive_breaches = self._consecutive_breaches + 1 if breach else 0
        return self._consecutive_breaches >= CONSECUTIVE_BREACHES_REQUIRED

    def explain(self) -> dict[str, Any]:
        return {
            "detector": self.name,
            "consecutive_breaches": self._consecutive_breaches,
            "threshold": self.decision_threshold,
            **self._last_explain,
        }

    def reset(self) -> None:
        """Clear hysteresis state. Not part of the frozen `AnomalyDetector`
        interface -- a duck-typed extension the Week 10 harness calls between
        fault episodes, so a breach streak building up at the tail of one
        episode (or during the normal windows before the next one starts)
        cannot borrow its way into the next episode's breach count and
        manufacture an artificially fast detection. See
        `docs/results/practice-run.md`, "zero-second detection delays"."""
        self._consecutive_breaches = 0
        self._last_explain = {}


@register("threshold_unscaled")
class UnscaledThresholdDetector(ThresholdDetector):
    """The pre-fix rule, kept **only** so the regression stays measurable.

    Identical to `ThresholdDetector` except that it takes the raw absolute
    deviation from a per-signal *mean* with no scaling -- which is what made
    the baseline silent (see this module's docstring and
    `docs/results/practice-run.md`). Keeping it registered means the BEFORE row
    of that comparison is regenerated from data by the same harness as the
    AFTER row, rather than being a number quoted from a previous run on a
    different dataset.

    Not a candidate detector: it is deliberately absent from
    `core.config.Settings.detector`'s allowed values, so nothing can select it
    at runtime.
    """

    name = "threshold_unscaled"

    def fit(self, X: list[MetricWindow], X_val: list[MetricWindow] | None = None) -> None:
        if not X:
            raise ValueError("need at least 1 training window")

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for window in X:
            for signal in DETECTOR_SIGNALS:
                for value in window.values.get(signal) or []:
                    sums[signal] = sums.get(signal, 0.0) + value
                    counts[signal] = counts.get(signal, 0) + 1
        if not sums:
            raise ValueError("training windows carry no detector signals")

        # Mean, not median -- and a spread of exactly 1.0 everywhere, which is
        # what "no scaling" means once `_residual` divides by it.
        self._median = {s: sums[s] / counts[s] for s in sums}
        self._spread = dict.fromkeys(sums, 1.0)

        residuals = [self._residual(window) for window in X]
        q1, q3 = _percentile(residuals, 25), _percentile(residuals, 75)
        self.decision_threshold = q3 + IQR_MULTIPLIER * (q3 - q1)
        self._consecutive_breaches = 0


@register("threshold_v2")
class FloorScaledThresholdDetector(ThresholdDetector):
    """`ThresholdDetector` with the v2 scaling floor always on
    (`docs/notes/scale-floor-v2.md`) -- the opt-in flag lives on the base
    class; this just defaults it on so the harness can select it by name,
    same pattern as `UnscaledThresholdDetector` above."""

    name = "threshold_v2"

    def __init__(self) -> None:
        super().__init__(use_scale_floor=True)
