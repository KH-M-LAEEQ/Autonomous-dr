# ADR-0002: Postgres for state, InfluxDB for telemetry

- **Status:** Proposed — accept at the Week 2 design review
- **Date:** 2026-08-__
- **Deciders:** BACKEND, FRONTEND, AI
- **Affects:** core/db.py, core/influx.py, the whole schema

## Context

TODO — write this in Week 1 together, in your own words. It is the part the
committee reads. Seed points:

- Telemetry is one append-only stream per signal, polled every 10s from Week 3 and never stopped: millions of rows, always queried as a time window.
- Incidents, votes, actions and the hash-chained audit log need transactions, foreign keys and joins.
- One store doing both jobs does one of them badly.

## Decision

Relational and auditable state lives in Postgres 16. Time-series telemetry lives
in InfluxDB 2.7, tagged by tenant and region. A detection row in Postgres names
the InfluxDB window it came from; telemetry is never copied into Postgres.

## Consequences

**Good:** TODO

**Bad:** TODO — name a real cost. Every one of these has one.

## Alternatives considered

| Option | Why not |
| --- | --- |
| TODO | TODO |

## Revisit when

InfluxDB retention or downsampling (Week 28) stops being enough, or a research
question needs joins across raw telemetry.
