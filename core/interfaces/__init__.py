"""The frozen contract.

Five interfaces plus PricingSource. After the Week 2 design review these
signatures do not change without an ADR and all three members agreeing in
writing. Adding a new IMPLEMENTATION is free and expected -- that is the whole
design.
"""

from core.interfaces.action_executor import ActionExecutor
from core.interfaces.anomaly_detector import AnomalyDetector
from core.interfaces.cloud_provider import CloudProvider
from core.interfaces.consensus_strategy import ConsensusStrategy
from core.interfaces.explanation_engine import ExplanationEngine
from core.interfaces.pricing_source import PricingSource

__all__ = [
    "ActionExecutor",
    "AnomalyDetector",
    "CloudProvider",
    "ConsensusStrategy",
    "ExplanationEngine",
    "PricingSource",
]
