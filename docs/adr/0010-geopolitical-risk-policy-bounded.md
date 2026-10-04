# ADR-0010: Geopolitical risk is policy-bounded, not an autonomous trigger

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-24
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** risk_signals (`source_type`, `source_url`), core/config.py (`w_risk_*`), Weeks 22, 25

## Context

The proposal claims the system reacts to geopolitical escalation. Letting live
headlines autonomously move production workloads is a poor idea: the signals are
noisy, a false positive costs real money, and a sentiment classifier would be
impossible to defend in the viva.

Provider-status signals (a cloud provider's own status page) are different: they
are factual, narrow and fast.

## Decision

Two kinds of risk signal, handled differently:

1. **`provider_status`** feeds the utility function autonomously, in real time.
2. **`geopolitical`** is computed continuously from a small set of hand-written,
   auditable rules over curated sources, and displayed transparently. Its **weight**
   in the utility function (`w_risk`) is a customer policy, bounded to
   `[w_risk_min, w_risk_max]` and overridable per tenant at onboarding, the same
   mechanism as the budget cap.

The score updates autonomously; only the bound on its weight is human-set. Every
`risk_signals` row stores `source_type` and `source_url`, so any heat-map cell can be
traced to its evidence. The Thompson Sampling bandit (Week 25) explores inside the
band and never widens it.

## Consequences

**Good:** the geopolitical claim stays honest and auditable, and a customer
can cap how much it can influence them. A rule that did not fire in a past event is
a reportable finding.

**Bad:** the system is deliberately less reactive than the proposal's wording
implies. The thesis must say so plainly.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Fully autonomous reaction to geopolitical news | Unsafe, undefendable, one bad feed away from an expensive false failover |
| Display only, no effect on decisions | Drops the cost-and-risk-aware claim entirely |

## Revisit when

The Week 22 backtest on the March 2026 and October 2025 windows. If the rules never
fire on real events, the rules are wrong or the claim is, and either goes in the
limitations chapter.
