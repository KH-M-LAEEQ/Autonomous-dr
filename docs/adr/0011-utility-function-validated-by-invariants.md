# ADR-0011: Utility function validated by invariants, not published values

**Status:** Accepted
**Date:** 2026-08-15
**Deciders:** AI, Backend, Frontend

---

## Context

The Week 5 plan says to unit-test `U` against Li et al.'s own worked values, and calls
that our correctness proof.

That test target does not exist. Li et al. (*J. Cyber Security and Mobility*, 14(5),
pp. 1173–1198) give the utility function as Eq. 7 but publish **no numeric values** for
`w_ability`, `w_cost`, `Φ_m`, or `U` anywhere in the paper. Tables 1–4 report system
outcomes — RTO, prediction latency, CPU load, consensus rounds — not utility
computations. No experiment in the paper isolates the utility function at all.

Two further gaps make a published-value test impossible even in principle:

- The paper specifies no normalisation for `C_failover`, so its numeric scale is
  undefined.
- `Φ_m` is computed from `x_{m,j}`, historical per-node performance on our own
  telemetry. There is no shared input to reproduce.

## Decision

Validate `U` by **invariants and scenario tests**, not by matching a number.

Invariants (Hypothesis, property-based):

- `U` strictly increases in `Φ`
- `U` strictly decreases in `cost`, `latency`, `impact`, `price_delta`, `risk`
- `U` strictly increases in `safety`
- Ranking is unchanged when any single term is uniformly scaled
- Weights sum to 1; every term normalised to `[0,1]` before weighting

Scenario tests (agreed behaviour):

- Cheap + reversible beats expensive + irreversible at equal effectiveness
- Cost over the tenant budget cap is refused regardless of `U`
- Single candidate is returned, not crashed on
- Identical candidates tie-break deterministically

Hypothesis moves from Week 27 to Week 5.

## Consequences

**Weaker in one way.** We cannot claim our implementation reproduces the source
paper's arithmetic. Nobody can — the arithmetic was never published.

**Stronger in another.** Li et al. assert the utility function without validating it.
Our Week 31 ablation is therefore the first empirical evidence that the formulation
does anything, which makes it a result rather than a reimplementation.

**Scope shift.** Roughly a day of Week 27's testing effort moves into Week 5. Week 27's
budget shrinks accordingly.

**Framing.** Our contribution is stated as *generalising* Li et al.'s two-term
node-selection utility into a seven-term action-selection utility — not as *extending a
validated equation*. See ADR-0012 if the framing is revisited.

**Weights are ours.** No published values exist, so the Week 5 hardcoded weights are a
project decision, tuned against the scenario tests above and learned by the Week 25
bandit within per-tenant policy bounds.
