# ADR-0002: Postgres for state, InfluxDB for telemetry

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** ALL

---

## Context

The system produces two kinds of data with almost nothing in common.

**State** — tenants, resources, incidents, decisions, votes, actions, cost estimates,
audit log. Relational, transactional, queried by joins, low volume, must never be lost.
The audit log is hash-chained and legally significant.

**Telemetry** — 20 signals per resource polled every 10 seconds, 24/7 from Week 3.
Append-only, never updated, queried by time range and tag, high volume. By Week 9 this
is ~200k timesteps and it keeps growing all year.

Forcing both into one store means either a relational database absorbing millions of
metric rows, or a time-series database pretending to do foreign keys and transactions.

## Decision

Postgres 16 (with pgvector) for state. InfluxDB for telemetry.

Telemetry is written with `tenant` and `region` tags. Postgres rows that need metric
context — a `detections` row, for instance — reference InfluxDB by tag plus time range,
not by foreign key.

## Consequences

**Two systems to run and back up.** Both are in `docker-compose.yml` from Week 1, so the
operational cost is paid once.

**No cross-store joins.** Correlating an incident with its metric window happens in
application code. Accepted — that correlation is a handful of queries, not a hot path.

**Retention is independent.** Week 28 sets InfluxDB downsampling and retention without
touching the audit log, which must be retained in full.

**Postgres stays small.** Index tuning in Week 28 is over thousands of rows, not
millions.
