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
| `li_utility` | TODO — Li et al. | Utility function `U(c, l, m)` |
| `liu_consensus` | TODO — Liu et al. | Consensus / voting model |
| `karami_anomaly` | TODO — Karami et al. | Anomaly scoring |

## 1. Utility function `U(c, l, m)` — `li_utility`, Eq. ??, p. ??

```
TODO: transcribe the equation exactly.
```

| Symbol | Meaning | Unit | Range | Source of the value at runtime |
| --- | --- | --- | --- | --- |
| `c` | cost | USD | ≥ 0 | `CostEstimate` from the active `PricingSource` |
| `l` | latency / recovery time | seconds | ≥ 0 | measured, or estimated per action type |
| `m` | TODO | | | |
| `w_c, w_l, w_m` | weights | — | sum to 1 | hardcoded in Week 5, learned in Week 25 |

**Normalisation:** TODO — how does each term get to a comparable scale? State it
explicitly; this is where implementations silently diverge from papers.

**Worked values from the paper** (the Week 5 unit test asserts these exactly):

| Case | `c` | `l` | `m` | Expected `U` | Paper reference |
| --- | --- | --- | --- | --- | --- |
| TODO | | | | | Table ?, p. ? |

**Extensions this project adds** — each one gets a row, because each one is a
contribution to defend:

| Week | Extra term | Why | Bounded by |
| --- | --- | --- | --- |
| 13 | blast-radius / impact score | cascade awareness from the dependency graph | `[0, 1]` |
| 21 | cross-cloud price delta | the "cost-aware" claim has to be real | budget gate |
| 22 | region risk score | proactive OSINT signal | `[0, 1]` |
| 25 | learned weights | Thompson sampling | hard bounds, cannot bypass the budget gate |

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
