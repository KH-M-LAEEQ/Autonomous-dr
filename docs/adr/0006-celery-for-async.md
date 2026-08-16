# ADR-0006: Celery for async orchestration

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

Several parts of the system are slow, unreliable, or scheduled, and none of them belong
in a request/response cycle:

- the collector, polling every 10 seconds, 24/7 from Week 3
- LLM explanation calls, which can take seconds and can fail entirely
- nightly model retraining with validation and rollback
- nightly fault injection runs
- Terraform plan and apply
- monthly savings report rollups

The hard requirement: **a recovery action must never wait for a language model.** If the
LLM API is down, recovery still happens.

## Decision

Celery with Redis as broker, running from Week 1's `docker-compose.yml`. Celery beat for
scheduled work.

The explanation engine is off the critical path — the action executes, a Celery task
generates the explanation, and it is pushed to the incident row and the UI when ready. A
template fallback covers API failure.

## Consequences

**Killing the LLM API does not stop recovery.** This is the Week 16 "done when", and it
falls out of the architecture rather than needing special handling.

**Scheduled work is declarative.** The collector and the nightly injector are beat tasks,
not cron plus scripts, so they are visible and restartable.

**Retrain rollback is contained.** Week 11's nightly retrain compares validation F1 and
reverts on regression, inside one task.

**Another moving part.** A worker that dies silently means detections stop. Worker health
belongs in the Week 28 load test and the Week 32 deployment check.

**Redis serves two roles** — Celery broker and state cache. Acceptable at our scale;
separate them if it becomes a bottleneck.
