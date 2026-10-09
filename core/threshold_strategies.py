"""Concrete ThresholdStrategy implementations (core/interfaces/anomaly_detector.py).

Adding a new implementation here needs no ADR -- only changes to the
ThresholdStrategy interface itself do. IQR is the harness default: lowest
observed false-positive rate of the four (docs/formulas.md §2).

Stdlib only (statistics/math), deliberately -- `core` must be importable
without the `ml` extra (numpy et al. are the AI role's tooling, see
pyproject.toml), and every AnomalyDetector needs a ThresholdStrategy default.
"""

import math
import statistics

from core.interfaces.anomaly_detector import ThresholdStrategy


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


class ZTestThreshold(ThresholdStrategy):
    """Flags residuals more than 3 standard deviations from the training mean."""

    SIGMA = 3.0

    def __init__(self) -> None:
        self._mean: float | None = None
        self._std: float | None = None

    def fit(self, train_residuals: list[float]) -> None:
        self._mean = statistics.fmean(train_residuals)
        self._std = statistics.pstdev(train_residuals)

    def is_anomalous(self, residual: float) -> bool:
        assert self._mean is not None and self._std is not None, "fit() not called"
        return abs(residual - self._mean) > self.SIGMA * self._std


class GaussianLikelihoodThreshold(ThresholdStrategy):
    """Flags residuals whose likelihood under the fitted Normal(mean, std) is
    below a cutoff. See docs/formulas.md §2.
    """

    def __init__(self, likelihood_cutoff: float = 1e-3) -> None:
        self._mean: float | None = None
        self._std: float | None = None
        self._likelihood_cutoff = likelihood_cutoff

    def fit(self, train_residuals: list[float]) -> None:
        self._mean = statistics.fmean(train_residuals)
        self._std = statistics.pstdev(train_residuals) or 1e-9

    def is_anomalous(self, residual: float) -> bool:
        assert self._mean is not None and self._std is not None, "fit() not called"
        z = (residual - self._mean) / self._std
        likelihood = math.exp(-0.5 * z**2) / (self._std * math.sqrt(2 * math.pi))
        return likelihood < self._likelihood_cutoff


class PercentileThreshold(ThresholdStrategy):
    """Flags residuals above the q-th percentile of training residuals (q95 default)."""

    def __init__(self, percentile: float = 95.0) -> None:
        self._cutoff: float | None = None
        self._percentile = percentile

    def fit(self, train_residuals: list[float]) -> None:
        self._cutoff = _percentile(train_residuals, self._percentile)

    def is_anomalous(self, residual: float) -> bool:
        assert self._cutoff is not None, "fit() not called"
        return residual > self._cutoff


class IQRThreshold(ThresholdStrategy):
    """Tukey's rule: flags residuals more than 1.5x the IQR above Q3.

    Default strategy (ADR-0009) -- lowest observed false-positive rate of the
    four, per docs/formulas.md §2.
    """

    MULTIPLIER = 1.5

    def __init__(self) -> None:
        self._upper: float | None = None

    def fit(self, train_residuals: list[float]) -> None:
        q1, q3 = _percentile(train_residuals, 25), _percentile(train_residuals, 75)
        self._upper = q3 + self.MULTIPLIER * (q3 - q1)

    def is_anomalous(self, residual: float) -> bool:
        assert self._upper is not None, "fit() not called"
        return residual > self._upper
