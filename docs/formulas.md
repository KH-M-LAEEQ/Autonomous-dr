# Formulas — the single source of truth

Week 1, AI role. Every formula the system implements is transcribed here **from the
paper, with the citation**, before any code uses it. Week 5 implements `U(c, l, m)`
against this file and unit-tests it on the paper's own worked values — that test is
the correctness proof, and it only works if the numbers below are the real ones.

Rules:

- Nothing here is written from memory. Open the PDF, copy the equation, note the
  equation number and page.
- If the paper is ambiguous, record the ambiguity and your chosen reading. Do not
  quietly pick one.
- If the implementation diverges from the paper, say so here and say why. A
  documented deviation is a design decision; an undocumented one is an error.

## Sources

| Key | Citation (fill in full, exactly as it will appear in the thesis) | Used for |
| --- | --- | --- |
| `li_utility` | Li et al., Eq. 7, p. 1183 | Utility function (extended, see ADR-0011) |
| `liu_consensus` | TODO — Liu et al. | Consensus / voting model |
| `karami_anomaly` | TODO — Karami et al. | Anomaly scoring |

## 1. Utility function — `li_utility` (Li et al., Eq. 7, p. 1183)

As published (scores candidate **nodes**):

```
U(cl_m) = w_ability * Phi_m - w_cost * C_failover(cl_m)
```

Ours (scores candidate **actions**; contract in ADR-0011, code in
`core/decision/utility.py`):

```
U = sum over present terms of  sign * weight * term

  + w_ability * ability        Phi: capability of the action's target. 1.0 until W3 data.
  - w_cost    * cost
  - w_latency * latency
  + w_safety  * safety         reversibility
  - w_impact  * impact         (W13)
  - w_price   * price_delta    (W21)
  - w_risk    * risk           (W22)
```

| Term | Meaning | Normalised against | Range | Ships |
| --- | --- | --- | --- | --- |
| `ability` | capability of the action's target (Li Phi) | already 0-1 | [0, 1] | W5 (stub 1.0) |
| `cost` | action cost | tenant budget cap | [0, 1] | W5 |
| `latency` | expected recovery time | 60 s target | [0, 1] | W5 |
| `safety` | reversibility of the action | tier table | [0, 1] | W5 |
| `impact` | blast radius | dependency graph | [0, 1] | W13 |
| `price_delta` | cross-cloud price gap | provider prices | [0, 1] | W21 |
| `risk` | region risk | risk score | [0, 1] | W22 |

**Rules:** every term is normalised to [0, 1] before weighting; signs live in a
registry (ability and safety add, the rest subtract); weights are non-negative and sum
to 1 over the present terms, so U is in [-1, 1]; an absent term is not a zero term and
a new term means a new `formula_version`; a `Decision` is only valid if `terms` and
`weights` have the same keys, `ability` is present and `utility` equals the formula.

**Hardcoded Week 5 weights:** ability 0.20, cost 0.25, latency 0.25, safety 0.30.
Week 25's bandit moves them inside per-tenant bounds and keeps the sum at 1.

**Worked values from the paper** (the Week 5 unit test asserts these exactly):

| Case | Expected `U` | Paper reference |
| --- | --- | --- |
| TODO: transcribe from Li et al. | | Table ?, p. ? |

Our own worked example (`core/tests/test_utility.py`): ability 1.0, cost 0.2,
latency 0.1, safety 0.9 with the weights above gives U = 0.395.

## 2. Anomaly score — `karami_anomaly`

```
TODO
```

Threshold rule (Week 4 baseline, never deleted): 3 consecutive breaches → detection.
Record the exact breach definition here, because every later detector is measured
against it.

### Threshold strategies (Week 10 comparison, ADR-0009)

`ThresholdStrategy` implementations (`core/threshold_strategies.py`), each fit on
training residuals only:

| Strategy | Rule | Notes |
| --- | --- | --- |
| Z-test | flag if `\|residual - μ\| > 3σ` | μ, σ from training residuals |
| Gaussian likelihood | flag if `N(residual; μ, σ) < cutoff` (default `1e-3`) | same μ, σ as Z-test |
| Percentile | flag if `residual > P95(train_residuals)` | q configurable, default 95 |
| IQR (Tukey) | flag if `residual > Q3 + 1.5 × (Q3 − Q1)` | **default** — lowest observed false-positive rate of the four in the Week 10 harness run |

TODO (Week 10, AI role): fill in the actual false-positive-rate numbers from
the harness run once it exists; the "lowest FPR" claim above is the design
rationale, the table here should be the proof.

## 3. Consensus — `liu_consensus`

Quorum: TODO — state the rule as a formula, not prose (`approvals ≥ ⌈(n+1)/2⌉` with
`n = 3`, timeout `T` seconds, and what happens on timeout).

PBFT (Week 24): safety bound `n ≥ 3f + 1`, so `f = 1` with `n = 4`. Note here what
that means for a 3-node deployment before Week 24 assumes otherwise.

## 4. Savings model (Week 23)

```
savings = downtime_cost_avoided - action_cost - system_overhead
```

Every term needs a stated assumption and a source. A defensible number beats an
impressive one — this table is what a committee will attack.

| Term | How it is computed | Assumption | Source |
| --- | --- | --- | --- |
| `downtime_cost_avoided` | TODO | TODO | TODO |
