"""The utility formula contract (ADR-0011)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.decision import add_term, score
from core.models import Decision

W5 = {"ability": 0.20, "cost": 0.25, "latency": 0.25, "safety": 0.30}
OPTION = {"ability": 1.0, "cost": 0.2, "latency": 0.1, "safety": 0.9}


def test_worked_example() -> None:
    # 0.20*1.0 - 0.25*0.2 - 0.25*0.1 + 0.30*0.9
    assert score(OPTION, W5) == pytest.approx(0.395)


def test_signs_good_adds_bad_subtracts() -> None:
    worse_cost = {**OPTION, "cost": 0.6}
    safer = {**OPTION, "safety": 1.0}
    assert score(worse_cost, W5) < score(OPTION, W5)
    assert score(safer, W5) > score(OPTION, W5)


def test_u_stays_inside_minus_one_to_one() -> None:
    best = {"ability": 1.0, "cost": 0.0, "latency": 0.0, "safety": 1.0}
    worst = {"ability": 0.0, "cost": 1.0, "latency": 1.0, "safety": 0.0}
    assert score(best, W5) == pytest.approx(0.5)
    assert score(worst, W5) == pytest.approx(-0.5)


def test_ability_is_required() -> None:
    with pytest.raises(ValueError, match="required"):
        score({"cost": 0.2}, {"cost": 1.0})


@pytest.mark.parametrize(
    ("terms", "weights", "msg"),
    [
        ({**OPTION, "cost": 1.5}, W5, "normalised"),
        (OPTION, {**W5, "cost": 0.30}, "sum to 1"),
        (OPTION, {k: v for k, v in W5.items() if k != "cost"}, "same keys"),
        ({**OPTION, "bogus": 0.1}, {**W5, "bogus": 0.0}, "unknown"),
    ],
)
def test_bad_formula_is_rejected(terms: dict, weights: dict, msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        score(terms, weights)


def test_adding_a_term_keeps_weights_summing_to_one() -> None:
    w = add_term(W5, "risk", 0.10)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["risk"] == 0.10
    assert w["cost"] == pytest.approx(0.25 * 0.9)
    assert score({**OPTION, "risk": 0.0}, w) == pytest.approx(0.395 * 0.9)


def test_absent_term_is_not_a_zero_term() -> None:
    # Same option, risk left out vs risk present at 0: different weight sets,
    # so they are different formulas and must carry different formula_versions.
    assert "risk" not in W5
    assert add_term(W5, "risk", 0.10) != W5


def test_decision_rejects_a_wrong_stored_utility() -> None:
    with pytest.raises(ValidationError):
        Decision(
            incident_id=uuid4(),
            chosen_action=None,
            utility=0.9,
            terms=OPTION,
            weights=W5,
            formula_version="w5-v1",
        )


def test_decision_accepts_a_correct_one() -> None:
    d = Decision(
        incident_id=uuid4(),
        chosen_action=None,
        utility=0.395,
        terms=OPTION,
        weights=W5,
        formula_version="w5-v1",
    )
    assert d.utility == pytest.approx(score(d.terms, d.weights))
