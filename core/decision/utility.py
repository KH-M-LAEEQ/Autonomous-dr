"""The utility formula, written once.

    U = sum over present terms of  sign * weight * term

Every term is normalised to [0, 1] BEFORE it gets here, so cost (dollars) and
latency (seconds) cannot swamp the others. Weights are non-negative and sum to 1,
so U always lies in [-1, 1] and scores from different formula versions are
comparable.

Signs live in this registry, never in the stored numbers. A stored term always
means "how much of this thing", so a saved decision can be re-scored later.

`ability` is Li et al.'s capability score (Phi): how healthy the place an action
moves traffic to is. Li scores nodes; we score actions, so Phi is the capability
of the action's target. Until the Week 3 collector has history it is 1.0 for every
option, which leaves the ranking unchanged but keeps the term in the record.

An absent term is NOT a zero term. Terms that have not landed yet are left out of
both `terms` and `weights`, and `formula_version` says which set was used.
"""

from dataclasses import dataclass
from math import isclose


@dataclass(frozen=True)
class TermSpec:
    key: str
    sign: int  # +1 helps the option, -1 hurts it
    week: int  # build week the term first ships
    meaning: str


TERMS: dict[str, TermSpec] = {
    t.key: t
    for t in (
        TermSpec("ability", +1, 5, "capability of the target node (Li Phi); 1.0 until data"),
        TermSpec("cost", -1, 5, "action cost, normalised against the tenant's budget cap"),
        TermSpec("latency", -1, 5, "expected recovery time, normalised against 60 s"),
        TermSpec("safety", +1, 5, "reversibility of the action"),
        TermSpec("impact", -1, 13, "blast radius from the dependency graph"),
        TermSpec("price_delta", -1, 21, "cross-cloud price gap"),
        TermSpec("risk", -1, 22, "risk of the target region"),
    )
}

# `ability` is the one term that must always be present: it is the paper's own term.
REQUIRED_TERMS = frozenset({"ability"})
_TOL = 1e-9


def validate_terms_and_weights(terms: dict[str, float], weights: dict[str, float]) -> None:
    """Raise ValueError unless terms and weights form a valid formula."""
    unknown = set(terms) - set(TERMS)
    if unknown:
        raise ValueError(f"unknown term(s): {sorted(unknown)}")
    missing = REQUIRED_TERMS - set(terms)
    if missing:
        raise ValueError(f"required term(s) missing: {sorted(missing)}")
    if set(terms) != set(weights):
        raise ValueError("terms and weights must have exactly the same keys")
    for key, value in terms.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"term {key!r} must be normalised to [0, 1], got {value}")
    for key, w in weights.items():
        if w < 0.0:
            raise ValueError(f"weight {key!r} must be non-negative, got {w}")
    if not isclose(sum(weights.values()), 1.0, abs_tol=_TOL):
        raise ValueError(f"weights must sum to 1, got {sum(weights.values())}")


def score(terms: dict[str, float], weights: dict[str, float]) -> float:
    """Return U for one option."""
    validate_terms_and_weights(terms, weights)
    return sum(TERMS[k].sign * weights[k] * terms[k] for k in terms)


def add_term(weights: dict[str, float], key: str, weight: float) -> dict[str, float]:
    """Return a new weight set with `key` added and the others scaled to keep sum 1.

    Use this when a later week adds a term, so the new formula_version stays
    comparable with the old one.
    """
    if key not in TERMS:
        raise ValueError(f"unknown term: {key!r}")
    if key in weights:
        raise ValueError(f"term {key!r} already present")
    if not 0.0 < weight < 1.0:
        raise ValueError("new weight must be between 0 and 1 (exclusive)")
    scaled = {k: w * (1.0 - weight) for k, w in weights.items()}
    scaled[key] = weight
    return scaled
