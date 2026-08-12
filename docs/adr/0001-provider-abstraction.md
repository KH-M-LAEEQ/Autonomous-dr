# ADR-0001: Provider abstraction behind one interface

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** core/interfaces/cloud_provider.py, every provider from Week 3 to Week 21

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- Four providers land across 19 weeks: simulated (W3), AWS (W7), Azure (W9), GCP (W21), Terraform (W20).
- GCP is cuttable at Gate A. Cutting it must not touch the decision engine.
- Free-tier quotas differ per provider; the interface has to survive that.

## Decision

Every cloud integration implements the single `CloudProvider` interface —
`get_health`, `list_resources`, `estimate_cost`, `execute`, `get_regions`.
Provider selection is configuration (`PROVIDERS=` in .env), never a code path.
Metrics from all providers are normalised onto the 20 canonical signals (Week 9).

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

A provider needs an operation that cannot be expressed as an action — that is a
new interface, not a wider one.
