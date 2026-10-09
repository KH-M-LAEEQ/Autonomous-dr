"""Rev. 2 shape changes to the frozen domain models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.models import Decision, RiskSourceType, Vote, VoteChoice


def test_decision_terms_are_a_dict_and_absent_keys_stay_absent() -> None:
    d = Decision(
        incident_id=uuid4(),
        chosen_action=None,
        utility=0.4,
        terms={"cost": 0.2, "latency": 0.1, "safety": 0.9},
        weights={"cost": 0.3, "latency": 0.3, "safety": 0.4},
        formula_version="w5-v1",
    )
    assert set(d.terms) == {"cost", "latency", "safety"}
    assert "impact" not in d.terms  # not zero-filled before Week 13


def test_decision_rejects_the_old_fixed_term_fields() -> None:
    with pytest.raises(ValidationError):
        Decision(  # type: ignore[call-arg]
            incident_id=uuid4(),
            chosen_action=None,
            utility=0.0,
            cost_term=0.0,
            weights={},
            terms={},
            formula_version="x",
        )


def test_vote_links_to_its_detection() -> None:
    det = uuid4()
    v = Vote(
        proposal_id=uuid4(),
        voter_id="node-b",
        choice=VoteChoice.APPROVE,
        detection_id=det,
        cast_at=datetime.now(UTC),
    )
    assert v.detection_id == det


def test_risk_source_types() -> None:
    assert {s.value for s in RiskSourceType} == {"provider_status", "geopolitical"}


def test_w_risk_bounds_are_ordered() -> None:
    s = Settings()
    assert s.w_risk_min <= s.w_risk_default <= s.w_risk_max
