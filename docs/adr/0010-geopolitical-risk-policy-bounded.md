# ADR-0010: Geopolitical risk is policy-bounded, not an autonomous trigger

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

The proposal commits to autonomous geopolitical threat detection: OSINT feeds detecting
military escalation and pre-emptively migrating workloads.

Taken literally, that means a sentiment classifier reading news and, on its own
authority, moving a customer's production infrastructure between continents. That is not
defensible. News sentiment is noisy, adversarially manipulable, and has no calibrated
relationship to whether a specific data centre is about to degrade. A false positive
costs the customer a live migration they did not ask for.

At the same time, the underlying observation is real and is the project's most
distinctive claim. Abandoning it entirely gives up the gap Potluri identifies.

## Decision

Separate the **score** from its **weight**.

**Provider-status risk is fully autonomous.** Status pages and RSS feeds are ingested
into `risk_signals` with `source_type = provider_status`, feed `U` directly, and shift
action selection with no human in the loop. This is the original plan, unchanged.

**Geopolitical risk is computed continuously and displayed transparently, but its
influence is bounded by customer policy.** The flag comes from a small set of
hand-written, auditable rules against curated sources — for example, two or more
corroborating status-tier sources reporting active escalation within a defined radius of
a provider facility within 48 hours — not from a sentiment classifier. Every row carries
a `source_url` for provenance.

The resulting score enters `U` as `terms["risk"]`, weighted by `w_risk`, bounded to
`[w_risk_min, w_risk_max]` set per tenant at onboarding — the same mechanism as the
budget cap. The score updates autonomously. The bound on its weight is the only
human-set part, and the Week 25 bandit explores inside the band without widening it.

## Consequences

**The claim survives, in a defensible form.** We do detect and display geopolitical risk,
autonomously and in real time. What a customer controls is how much it is allowed to
move their infrastructure.

**Provenance is visible.** The Week 22 risk heat map clicks through to the contributing
`risk_signals` rows and their source URLs. An operator can always see why a region is
orange.

**The backtest has two independent parts.** (1) Provider-status lead time — minutes
between a provider's status post and our own health-check detection, across past
incidents, reported as a distribution. (2) Geopolitical rule backtest — apply the flag
retroactively to the March 2026 and October 2025 windows and report honestly whether it
would have fired. **A negative result on part 2 is a legitimate finding**, not a failed
week.

**Rules, not a model.** Hand-written rules are auditable and explainable in a viva. A
classifier's decision boundary is neither, and there is no labelled training set for
"escalation that precedes cloud degradation" anyway.
