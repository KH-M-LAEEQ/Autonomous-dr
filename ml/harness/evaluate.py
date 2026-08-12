"""The evaluation harness -- Week 10, and the highest-leverage thing in the ml/ tree.

Rules that must never be broken, because every number in your thesis depends on them:
  1. Time-based split. First 70% train, last 30% test. NEVER shuffle telemetry.
  2. Identical splits for every detector, every time.
  3. Report precision, recall, F1, false-positive rate, and detection delay in seconds.
  4. Bad results go in the table too.

Week 31 requires `make results` to regenerate every thesis figure from raw data
via this module. Design for that now; retrofitting it in March is miserable.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalResult:
    """One row of the results table. Keep the field names stable -- the thesis
    tables and the dashboard both read them."""

    detector: str
    dataset_version: str
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    detection_delay_p50_s: float
    detection_delay_p95_s: float
    n_episodes: int
    seed: int = 0
    notes: str = ""
    extra: dict[str, float] = field(default_factory=dict)


def time_based_split(n: int, train_fraction: float = 0.7) -> tuple[slice, slice]:
    """Chronological split. The only splitting function allowed in this project."""
    cut = int(n * train_fraction)
    return slice(0, cut), slice(cut, n)


def evaluate(detector_name: str, dataset_version: str) -> EvalResult:
    """Score one detector on one dataset version. Week 10 -- AI role."""
    raise NotImplementedError("Week 10 -- AI")
