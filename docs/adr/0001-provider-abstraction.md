# ADR-0001: Provider abstraction behind one interface

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

The system must operate across AWS, Azure and GCP. Their SDKs disagree on almost
everything: metric names, region identifiers, resource models, auth, pagination, error
semantics. Writing provider-specific code paths through the application means every new
feature is written three times and every new provider is a refactor.

We also need a fake provider from Week 3 — before any real cloud account is wired up —
so the full loop can be built and demoed without spending money or waiting on IAM.

## Decision

One abstract `CloudProvider` interface in `core/interfaces/`, with five methods:

```
get_health()
list_resources()
estimate_cost(action)
execute(action)
get_regions()
```

Every provider — `SimulatedProvider`, `AWSProvider`, `AzureProvider`, `GCPProvider` —
implements it. Nothing above the interface knows which provider it is talking to.
Selecting a provider is a config change.

A metric normalisation layer (Week 9) maps each provider's native metrics onto our 20
canonical signals, so `get_health()` returns the same shape regardless of source.

## Consequences

**Adding a provider is an implementation, not a refactor.** GCP in Week 21 is a new
class, not a change to the decision engine, the dashboard, or the schema.

**The simulator is a first-class provider.** Not a test double bolted on the side — it
satisfies the same contract, so the Week 6 end-to-end demo exercises the real code path.

**The interface is a lowest common denominator.** Anything one provider can do that the
others cannot either gets left out or hidden behind `execute(action)`. Accepted: the
alternative is leaking provider specifics upward.

**Frozen after Week 2.** Changing a signature costs an ADR and all three agreeing in
writing. Adding an implementation is free and expected.
