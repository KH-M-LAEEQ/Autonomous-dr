# ADR-0006: Celery for asynchronous and scheduled work

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** core/tasks.py, the collector (Week 3), nightly retrain (Week 11), explanations (Week 16)

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- The collector must poll every 10 seconds, unattended, for 30+ weeks.
- LLM explanation must be off the critical path: the action cannot wait for it.
- Nightly retraining and nightly fault injection are cron-shaped work.
- Redis is already in the stack as a broker; adding Kafka or Temporal is not free.

## Decision

Celery with a Redis broker runs all background and scheduled work. Celery beat
owns the 10-second collector poll and the nightly jobs. Anything that can fail
slowly runs as a task, not inside a request.

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

Task volume or ordering guarantees outgrow Redis — not expected at this scale.
