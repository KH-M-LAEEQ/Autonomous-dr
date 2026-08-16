# ADR-0007: Simulator-first testing

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

Development against real cloud accounts is slow, costly and destructive. Provisioning
takes minutes, faults cannot be induced on demand, ground truth is approximate, and a
mistake produces a bill. AWS Fault Injection Service is billed per action-minute — a
validation tool, not a development one.

We also need a working end-to-end loop by Week 6 (Gate A), before real cloud write paths
exist.

## Decision

`SimulatedProvider` implements `CloudProvider` (ADR-0001) and is built first, in Week 3:
8 resources across 3 fake regions, 2 fake tenants, realistic metrics with daily
seasonality and noise, and fault injection via API.

All development and all automated testing runs against it. Real providers are added
read-only first (AWS Week 7, Azure Week 9), with the first real write action in Week 12
on throwaway resources, dry-run before live.

Week 8's Docker microservice testbed with scripted fault injection extends the same
principle to the ML dataset: exact fault start, end, type and target written to
`labels.jsonl`.

## Consequences

**Gate A is reachable in Week 6** with no real cloud dependency.

**Ground truth is exact.** The injector knows precisely when each fault began, so
detection delay (`docs/formulas.md` §2) is measured, not estimated. This is more rigorous
than opportunistic observation of real outages, and should be stated as such rather than
apologised for.

**The dataset accumulates unattended.** Nightly runs from Week 8 mean Week 10 training
has six weeks of data without anyone doing anything.

**Real risk: simulated faults may be too easy.** If Week 8's fault types are trivially
detectable, the Week 4 threshold baseline could beat the ML detectors and Gate B fails
for the wrong reason. Mitigation: vary fault magnitude and onset rate, include gradual
degradation and not just hard stops, and review the fault catalogue before Week 10.

**One real validation run.** Week 26's AWS FIS experiment is budgeted, run once or twice,
and fully captured — it is the row in the validation matrix that says the system works
outside the simulator.
