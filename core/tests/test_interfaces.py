"""Contract tests for the frozen interfaces.

These fail loudly if someone changes a signature without an ADR. That is the
point -- this file is the enforcement mechanism for the Week 2 freeze.
"""

import inspect
from abc import ABCMeta

from core.interfaces import (
    ActionExecutor,
    AnomalyDetector,
    CloudProvider,
    ConsensusStrategy,
    ExplanationEngine,
    PricingSource,
    ThresholdStrategy,
)

EXPECTED: dict[ABCMeta, set[str]] = {
    CloudProvider: {"get_health", "list_resources", "estimate_cost", "execute", "get_regions"},
    AnomalyDetector: {"fit", "score", "explain"},
    ThresholdStrategy: {"fit", "is_anomalous"},
    ConsensusStrategy: {"propose", "vote", "commit"},
    ActionExecutor: {"dry_run", "execute", "rollback", "tier"},
    ExplanationEngine: {"explain"},
    PricingSource: {"unit_price", "is_available"},
}


def test_frozen_method_sets() -> None:
    for interface, methods in EXPECTED.items():
        assert interface.__abstractmethods__ == frozenset(methods), (
            f"{interface.__name__} changed. If this is deliberate, write an ADR "
            f"in docs/adr/ and update this test in the same PR."
        )


def test_every_abstract_method_is_documented() -> None:
    for interface in EXPECTED:
        for name in interface.__abstractmethods__:
            member = inspect.getattr_static(interface, name)
            func = member.fget if isinstance(member, property) else member
            assert func.__doc__, f"{interface.__name__}.{name} needs a docstring"
