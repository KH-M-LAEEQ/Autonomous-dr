# ADR-0011: One fixed contract for the utility formula

- **Status:** Proposed
- **Date:** 2026-10-05
- **Deciders:** AI, BACKEND
- **Affects:** `core/decision/utility.py`, `Decision` (`terms`, `weights`, `formula_version`), Weeks 5, 13, 21, 22, 25

## Context

The formula gains terms over the build, but three things were left open: where
Li's capability score (Phi) is stored, whether weights must add up to 1, and which
terms add or subtract. Without an answer, a saved decision could not be re-scored,
and scores from different weeks could not be compared.

## Decision

1. **Phi is the term `ability`.** It is stored in `Decision.terms` like every other
   term and is the only required one. Li scores nodes and we score actions, so for
   an action it is the capability of the node or region the action moves traffic to.
   Until the Week 3 collector has history it is 1.0 for every option, which does not
   change the ranking but keeps the term in the record.
2. **Every term is normalised to [0, 1] before weighting.** Cost against the budget
   cap, latency against the 60-second target. A stored term always means "how much
   of this thing".
3. **Signs live in a registry, not in the numbers.** `ability` and `safety` add;
   `cost`, `latency`, `impact`, `price_delta` and `risk` subtract.
4. **Weights are non-negative and sum to 1** over the terms that are present. U is
   therefore always between -1 and 1. When a later week adds a term, `add_term`
   scales the existing weights so the sum stays 1.
5. **Absent is not zero.** A term that has not landed is missing from both `terms`
   and `weights`. A new term means a new `formula_version`.
6. **A `Decision` cannot be saved unless it is consistent**: same keys in `terms`
   and `weights`, `ability` present, and `utility` equal to the formula result.
7. **Week 25's bandit** moves weights only inside the per-tenant bounds and keeps
   them summing to 1. `w_risk` stays in `[w_risk_min, w_risk_max]` (ADR-0010).

## Consequences

- Any saved decision can be re-scored from its own record, which the audit log and
  the explanation engine rely on.
- Adding impact (W13), price_delta (W21) or risk (W22) is one registry-backed
  call, not a model change.
- Raw dollar and second values stay in `cost_estimates` and the action record; the
  normalising functions belong to Week 5.

## Follow-ups outside this ADR

- The FYP document states a three-term formula (ability, cost, safety). The build
  plan adds latency in Week 5. Word it as "three-term core, extended by latency and
  later terms".
- The Week 5 plan lists `Decision.terms` as cost, latency and safety only. It
  should also list `ability`.
