# formulas.md

## §1 Utility function

**Source:** Li et al., *J. Cyber Security and Mobility*, 14(5), pp. 1173–1198, 2025.
doi: 10.13052/jcsm2245-1439.1456

### As published (Eq. 7, p. 1183)

```
U(cl_m) = w_ability · Φ_m − w_cost · C_failover(cl_m)
cl_opt  = arg max U(cl_m)                              (Eq. 8)
```

Two terms. Scores candidate **nodes**.

### Capability score (Eq. 3–4, p. 1180)

```
w_j = E(θ_j) / Σ E(θ'_j)          weights, sum to 1
Φ_m = Σ w_j · nor(x_{m,j})        capability of node cl_m
```

`x_{m,j}` = historical performance of node `m` on metric `j`. Comes from the Week 3
collector. Until it has data, stub `Φ = 1.0`.

### Ours (contract fixed in ADR-0011, code in `core/decision/utility.py`)

```
U = Σ sign_k · w_k · term_k        over the terms that are present

  + w_ability · ability            Φ, capability of the action's target. 1.0 until W3 data.
  − w_cost    · cost
  − w_latency · latency
  + w_safety  · safety
  − w_impact  · impact             (W13)
  − w_price   · price_delta        (W21)
  − w_risk    · risk               (W22)
```

Scores candidate **actions**, not nodes. Li scores nodes, so for an action `ability` is
the capability of the node or region the action moves traffic to. Implemented as a
terms dict so keys can be added without touching the code that consumes it.

**Rules (the formula contract):**

1. **`ability` is a term.** It is stored in `Decision.terms` like the others and is the
   only required one. It is Φ. Before Week 3 history exists it is 1.0 for every option,
   which leaves the ranking unchanged but keeps the term in the record.
2. **Every term is normalised to [0, 1] before weighting.** Stored terms always mean
   "how much of this thing". Raw dollars and seconds live in `cost_estimates` and the
   action record, not in `terms`.
3. **Signs live in a registry, not in the numbers.** `ability` and `safety` add (safety
   is reversibility). Everything else subtracts.
4. **Weights are non-negative and sum to 1** over the terms that are present, so U is
   always in [−1, 1] and scores from different formula versions are comparable. When a
   later week adds a term, `add_term` scales the existing weights so the sum stays 1.
5. **A `Decision` is only valid if** `terms` and `weights` have the same keys, `ability`
   is present, and `utility` equals the formula result. A saved decision can always be
   re-scored from its own record.

---

## §1.1 The terms

### Week 5 — implement these four now

| Term | What it is | Why it's here | Source |
|---|---|---|---|
| `ability` | capability of the action's target node, 0–1 (Li's Φ) | The paper's own term. Without it the formula is not an extension of Li, and a decision can't be re-scored from its record. Stub 1.0 until the collector has history. | W3 collector, entropy weights over the Φ subset in `metric-schema.md` |
| `cost` | dollar cost of the action, normalised against the tenant's budget cap | Li's `C_failover`. Without it the system picks the most expensive recovery every time. Also feeds the budget gate. | `PricingSource` — static table W5, live APIs W12 |
| `latency` | expected recovery time, normalised against the 60 s target | Our 60-second target is a hard requirement. A cheap action that takes 20 minutes fails the objective. Li has no time term. | measured per action type |
| `safety` | reversibility, 0–1 | **This is the novel term.** A DNS weight shift is undoable in seconds; a DR promotion is not. Without it the system treats "reroute traffic" and "promote the standby region" as interchangeable if the cost matches. | static per action tier |

### Week 13 — after the dependency graph exists

| Term | What it is | Why it's here | Source |
|---|---|---|---|
| `impact` | blast radius, 0–1 | An action that fixes one service but takes down four downstream is a net loss. Can't be computed until we have the service graph. | NetworkX reachability over `graph_nodes` / `graph_edges` |

### Week 21 — after the third provider is live

| Term | What it is | Why it's here | Source |
|---|---|---|---|
| `price_delta` | cost gap between providers | Backs the "cost-aware multi-cloud" claim. Meaningless with one provider — needs at least two live to compare. | AWS Price List + Azure Retail + GCP Billing APIs |

### Week 22 — after the risk feed exists

| Term | What it is | Why it's here | Source |
|---|---|---|---|
| `risk` | region risk, 0–1 | Stops the system failing over *into* a degrading region. Provider-status risk is autonomous; `w_risk` is bounded per tenant (ADR-0010). | `risk_signals` table, §5 |

### Why all seven are in the file when only four ship this week

`Decision.terms` is a dict from Week 2. If it were fixed float fields, adding
`impact` in November means a schema migration, a model change, and re-running every
result generated before it. Writing the full key set down now costs nothing and means
Weeks 13 / 21 / 22 are one-line additions.

Absent key ≠ zero-weighted key. Don't zero-fill terms that haven't landed —
`formula_version` history depends on telling those apart. A new term means a new
`formula_version`, with the old weights scaled so the set still sums to 1.

---

## §1.2 Things the paper leaves to us

- **No weight values given.** We pick them. Hardcoded W5 (ability 0.20, cost 0.25,
  latency 0.25, safety 0.30), learned by the bandit W25.
- **Normalise every term to [0,1] before weighting.** `Φ` is 0–1, cost is currency —
  subtract them raw and cost swamps everything.
- **`w_j` is derived from data (Eq. 3). The outer weights are tuned.** Week 25's
  bandit touches only the outer ones, stays inside the per-tenant bounds, and keeps
  the weights summing to 1.

---

## §2 Detection metrics

**Source:** Karami, Jalali & Ghassemi, arXiv:2510.11141, Oct 2025.
(arXiv preprint — not IEEE Access. Fix the reference list.)

Week 10's harness uses these definitions and never changes them. Every result in the
thesis inherits them, so a redefinition in March invalidates everything before it.

### From the paper (Eqs. 21–23)

```
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 · Precision · Recall / (Precision + Recall)
FPR       = FP / (FP + TN)
```

Point-wise, computed against per-timestamp ground-truth labels.

### Detection delay — ours

**The paper has no timing metric.** It reports Precision, Recall, F1, Accuracy, AUC and
FPR only. So we define delay ourselves:

```
delay = t_first_detection − t_fault_injected      (seconds)
```

Measured per episode. Week 8's injector writes exact fault start/end to
`labels.jsonl`, so ground truth is exact. Report the distribution (p50 / p95 / p99),
not the mean. Undetected faults are excluded from the delay distribution and counted
separately as misses — averaging them in as zero or infinity both lie.

### Threshold method — use IQR, not Z-test

Their Table V, on LSTM residuals:

| Method | F1 | FPR |
|---|---|---|
| Z-test (3σ) | 0.688 | 0.215 |
| Gaussian likelihood | 0.688 | 0.215 |
| Percentile (q95) | 0.652 | 0.238 |
| **IQR (Tukey 1.5×)** | 0.621 | **0.189** |

IQR gives the lowest false-positive rate for a small F1 cost. Our proposal commits to
near-zero false actions, so that's the right trade. Z-test stays available via config
for the comparison table.

```
IQR rule:  anomaly if  r < Q1 − 1.5·IQR  or  r > Q3 + 1.5·IQR
```

Quartiles fit on **training** residuals only.

### Split — 70 / 15 / 15

Train 70%, validation 15%, test 15%. Strictly temporal, never shuffled. The val set is
what early stopping monitors; a 70/30 split has nowhere to stop from. `μ` and `σ` for
normalisation come from training data only.

### Residual detection (Week 11 LSTM)

```
r_j = x_j − x̂_j
```

Their LSTM config, which our Week 11 spec should match: 2 layers, 64 hidden units,
dropout 0.2, window 50, Adam @ 1e-3, batch 32, gradient clip 1.0, early stopping
patience 5. Converges in 10–20 epochs.

> **Don't use their F1 numbers as a baseline to beat.** Reported precision (0.688)
> isn't consistent with reported FPR (0.215) under the class imbalance they describe.
> Our baseline is the Week 4 threshold detector on our own data.

---

## §3 Consensus

**Source:** Liu et al., *Scientific Reports*, 13:13030, 2023.
doi: 10.1038/s41598-023-28856-x

Cite this for PBFT mechanics only. The paper is about consortium blockchain
throughput — it says nothing about monitors, anomaly detection, or false positives.
The three-heterogeneous-detector design in Week 17 is ours.

### Node count

```
n ≥ 3f + 1        →  f = 1 needs n = 4, not 3
```

Quorum default: n = 3. PBFT: n = 4. Assert it at construction.

### Phase thresholds

| Phase | Votes needed | At n=4, f=1 |
|---|---|---|
| Prepare | `2f + 1` | 3 |
| Commit | `2f + 1` | 3 |
| Client reply | `f + 1` | 2 |

> **The paper is wrong here.** Liu et al. (p. 3) state the prepare phase requires
> `3f + 1` messages. It's `2f + 1`. Using `3f + 1` at n=4 means all four nodes must
> respond, so a single node death stalls consensus — which fails Week 17's "a killed
> node doesn't stop legitimate recovery." Their commit (`2f+1`) and reply (`f+1`)
> numbers are correct.

### Do not implement CBFT

CBFT is the paper's own contribution — node grouping plus credit scoring. Built for
50–600 nodes; their Fig. 5 shows it is *slower* than plain PBFT below ~28 nodes
because grouping overhead dominates. We run 4. Implement plain PBFT
(Castro & Liskov).

Also: the paper claims CBFT tolerates up to 1/2 Byzantine nodes in some groups. That
exceeds the classical BFT bound. Don't repeat the claim.

### Message overhead — W24 benchmark

```
T_PBFT = 2N(N − 1)        # N=4  →  24 messages/round
T_quorum ≈ 2(N − 1)       # N=3  →   4 messages/round
```

Latency, same source:

```
T_d = T_c − T_r           # confirmation time − generation time
```

This is the quorum-vs-PBFT trade-off table for Week 24.

---

## §4 Savings model

TODO — W23.

---

## §5 Risk score

```
risk_score = clamp(a₁·incident_density + a₂·advisory_severity + a₃·geopolitical_flag, 0, 1)
```

green `< 0.33` · orange `0.33–0.66` · red `≥ 0.66`

Feeds `terms["risk"]` above.
