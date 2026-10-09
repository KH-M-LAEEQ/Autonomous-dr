"""Value objects that cross interface boundaries.

These are as frozen as the interfaces themselves -- an interface signature is
only as stable as the types in it. Pydantic so FastAPI can serialise them
directly and so bad data fails at the boundary instead of three layers in.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import (
    ActionStatus,
    ActionTier,
    ActionType,
    HealthState,
    IncidentState,
    ProviderName,
    VoteChoice,
)


class Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Resource(Base):
    """Anything a provider can report health for: an instance, a service, a zone."""

    id: str
    provider: ProviderName
    region: str
    tenant_id: str
    kind: str
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricWindow(Base):
    """A slice of telemetry handed to a detector.

    `values` maps one of the 20 canonical signal names to its series, oldest
    first. Every detector -- threshold, IForest, LSTM, GNN -- receives this
    exact shape, which is what makes the benchmark harness possible.
    """

    resource_id: str
    tenant_id: str
    start: datetime
    end: datetime
    step_seconds: int
    values: dict[str, list[float]]


class HealthReport(Base):
    resource_id: str
    state: HealthState
    observed_at: datetime
    signals: dict[str, float] = Field(default_factory=dict)
    message: str | None = None


class Detection(Base):
    """One detector's verdict on one window."""

    id: UUID = Field(default_factory=uuid4)
    resource_id: str
    tenant_id: str
    detector: str
    score: float
    is_anomaly: bool
    detected_at: datetime
    model_version: str | None = None
    explanation: dict[str, Any] = Field(default_factory=dict)


class Incident(Base):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    resource_id: str
    state: IncidentState = IncidentState.OPEN
    opened_at: datetime
    closed_at: datetime | None = None
    trigger_detection_id: UUID | None = None


class Action(Base):
    """A candidate remediation. Immutable: a modified plan is a new Action."""

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID | None = None
    tenant_id: str
    provider: ProviderName
    type: ActionType
    tier: ActionTier
    target_resource_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.PROPOSED


class CostEstimate(Base):
    """Written to cost_estimates BEFORE execution. The budget gate reads this."""

    action_id: UUID
    currency: str = "USD"
    one_off_usd: float = 0.0
    hourly_usd: float = 0.0
    projected_monthly_usd: float = 0.0
    confidence: float = 0.5
    source: str = "static_table"
    breakdown: dict[str, float] = Field(default_factory=dict)


class Decision(Base):
    """Output of the utility function. `utility` is the ranked score.

    `terms` is a dict, not fixed fields, because the formula gains keys over the
    build (cost/latency/safety in W5, impact W13, price_delta W21, risk W22; see
    docs/formulas.md section 1.1). A key that has not landed yet is ABSENT, never
    zero-filled: an absent term and a zero-weighted term mean different things once
    `formula_version` history matters.
    """

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    chosen_action: Action | None
    utility: float
    terms: dict[str, float]
    weights: dict[str, float]
    formula_version: str
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str | None = None


class Proposal(Base):
    """What gets voted on. Same object under quorum and under PBFT."""

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    action: Action
    proposer_id: str
    created_at: datetime
    digest: str | None = None  # SHA-256 over the canonical action; PBFT needs it


class Vote(Base):
    proposal_id: UUID
    voter_id: str
    choice: VoteChoice
    # The Detection this vote was based on. Under heterogeneous detectors (ADR-0012)
    # a vote is only explainable if you can see which detector produced it.
    detection_id: UUID | None = None
    reason: str | None = None
    cast_at: datetime


class ConsensusResult(Base):
    proposal_id: UUID
    committed: bool
    votes: list[Vote]
    strategy: str
    latency_ms: float
    message_count: int = 0
    note: str | None = None


class ExecutionResult(Base):
    action_id: UUID
    status: ActionStatus
    started_at: datetime
    finished_at: datetime | None = None
    provider_ref: str | None = None
    actual_cost_usd: float | None = None
    error: str | None = None
    rollback_token: str | None = None


class ExplanationContext(Base):
    """Everything the explanation engine is allowed to see. Nothing else.

    The LLM must cite only what is in `retrieved_documents`; if it says anything
    not grounded here, that counts as a hallucination in the Week 16 audit.
    """

    incident: Incident
    detections: list[Detection]
    decision: Decision | None = None
    consensus: ConsensusResult | None = None
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    topology_summary: str | None = None
