"""Enums shared by every interface. Adding a member is free; renaming one is a
breaking change to the frozen contract and needs an ADR.
"""

from enum import StrEnum


class ProviderName(StrEnum):
    SIMULATED = "simulated"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    TERRAFORM = "terraform"


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class IncidentState(StrEnum):
    """State machine implemented in Week 4. Transitions are validated, not assumed."""

    OPEN = "open"
    DECIDING = "deciding"
    ACTING = "acting"
    RESOLVED = "resolved"
    FAILED = "failed"


class ActionTier(StrEnum):
    """Tier 1 is reversible in seconds. Tier 3 needs human approval (Week 17)."""

    TIER_1 = "tier_1"  # DNS weight shift, traffic reroute
    TIER_2 = "tier_2"  # scaling, region failover
    TIER_3 = "tier_3"  # full DR promotion -- human approval required


class ActionType(StrEnum):
    DNS_WEIGHT_SHIFT = "dns_weight_shift"
    TRAFFIC_REROUTE = "traffic_reroute"
    SCALE_OUT = "scale_out"
    REGION_FAILOVER = "region_failover"
    CROSS_CLOUD_FAILOVER = "cross_cloud_failover"
    DR_PROMOTION = "dr_promotion"
    NO_OP = "no_op"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED_BY_BUDGET = "rejected_by_budget"
    REJECTED_BY_CONSENSUS = "rejected_by_consensus"
    AWAITING_HUMAN = "awaiting_human"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class VoteChoice(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class DetectorName(StrEnum):
    """Every detector ever benchmarked appears here so the results table can key off it."""

    THRESHOLD = "threshold"
    IFOREST = "iforest"
    LOF = "lof"
    ECOD = "ecod"
    COPOD = "copod"
    AUTOENCODER = "autoencoder"
    LSTM = "lstm"
    ENSEMBLE = "ensemble"
    GNN = "gnn"


TIER_ORDER: dict[ActionTier, int] = {
    ActionTier.TIER_1: 1,
    ActionTier.TIER_2: 2,
    ActionTier.TIER_3: 3,
}
"""Explicit ordering. Do not rely on StrEnum alphabetical comparison -- it happens
to work today and will break the first time someone renames a tier."""
