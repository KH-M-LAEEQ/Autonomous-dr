# Worker concurrency pinned to 1 -- a stopgap, not the fix

- **Status:** Proposed
- **Date:** 2026-10-09
- **Affects:** `ml/tasks.py` (`_history`, `_fitted`, `_detectors`), `docker-compose.yml`'s `worker` service

## What's wrong

`ml/tasks.py` accumulates detector bootstrap history and fit state in plain
module-level Python dicts (`_history`, `_fitted`, `_detectors`), scoped to
whatever process the module happens to be imported in. Celery's default
prefork pool runs one worker process per CPU -- confirmed in this
environment: `concurrency: 8 (prefork)`. `detect_anomalies` is dispatched to
whichever of those 8 processes is free for a given 10s tick, and each
process has its OWN independent copy of `_history` -- there is no IPC, lock,
or shared store tying them together.

`FIT_WINDOW_COUNT = 30` means a resource's detector only fits once some
single process has individually accumulated 30 ticks' worth of history for
it. With 8 processes splitting ticks, that only happens if one process
gets lucky enough to receive ~30 consecutive (or heavily lopsided)
dispatches. Observed directly: the same warm-up wait that completed in
~162-230s on several runs simply never completed within a 420s (7-minute)
budget on another, with no error anywhere in the worker logs -- every
`detect_anomalies` tick "succeeded", just never resolved any single
process's own history past the threshold.

## Why this note instead of a fix

Pinning `--concurrency=1` (this commit) makes bootstrap deterministic by
removing the fragmentation entirely -- one process, one `_history` dict,
every tick lands on it. It is NOT the right long-term design: it also
serializes `collect_telemetry` and `detect_anomalies` (and now
`core.incident_tasks.process_incident`, since all three share the single
worker) onto one process, so a slow task can delay the next tick of
everything else. For 8 simulated resources this costs nothing meaningful
today, but it does not scale and it does not fix the actual problem --
it just makes the single-process path reliable enough for local
verification.

## The real fix (not implemented here)

Make detection state external to the worker process instead of in-memory:

- Fit from InfluxDB's own history (`core.influx.query_recent_window` over a
  longer range) rather than accumulating `MetricWindow`s in a Python list
  across ticks -- removes the need for `_history` to persist across calls
  at all.
- Store the fitted detector's parameters (or a serialized model) somewhere
  all worker processes can read -- Redis, matching `core.detector_state`'s
  existing pattern for the `detector_fitted` flag itself, or a dedicated
  table.
- `_detectors`'s per-resource `AnomalyDetector` instances would need the
  same treatment, or `is_anomaly`'s consecutive-breach counter (also
  in-memory, also per-process) has the identical fragmentation problem on
  the SCORING path, not just the fit path -- worth checking once the fit
  path is fixed, since it may already be silently under-counting breaches
  the same way.

## Who's affected

Simulated local dev/demo only, with the current frozen `AnomalyDetector`/
`ThresholdDetector` design. Not urgent to fix immediately, but worth an ADR
before any production provider makes an idle, state-fragmented worker pool
more than an annoyance.
