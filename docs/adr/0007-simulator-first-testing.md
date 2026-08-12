# ADR-0007: Simulator-first development and testing

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** SimulatedProvider (Week 3), SimulatedExecutor (Week 5), every test, the cost risk register entry

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- Free-tier cloud accounts are rate-limited, slow to fail on demand, and billable. Breaking real infrastructure 200 times to test a state machine is not affordable.
- A demo must work with WiFi disabled (Week 35 rehearsal requirement).
- Fault injection with exact ground truth is what makes the Week 10 evaluation harness honest.

## Decision

Every feature is built and tested against `SimulatedProvider` and
`SimulatedExecutor` first, with injectable faults and known ground truth. Real
providers are validated on top of a working simulated path, not instead of one.
CI never touches a real cloud account.

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

Never. The real-cloud validation runs (Week 12, Week 26) sit on top of this, they
do not replace it.
