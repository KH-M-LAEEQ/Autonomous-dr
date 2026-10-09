"""Autonomous incident processing -- the Celery task that makes the loop run
without a human (or smoke.py) calling `run_incident` by hand.

`ml.tasks.detect_anomalies` enqueues `process_incident` the moment it opens a
new incident. This module lives in `core`, not `ml`, so `run_incident` and
its concrete `PricingSource`/`ActionExecutor`/`ConsensusStrategy` can be
constructed without `core` importing `ml` (see `core/__init__.py`'s rule) --
`ml.tasks` imports this task, not the other way around.

Exactly once, even under a retried or duplicated task delivery: `core.
incidents.claim_incident`'s atomic OPEN -> DECIDING transition is the lock.
A second delivery for the same incident finds it already past OPEN and
returns without calling `run_incident` again.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from core.consensus.quorum import QuorumConsensus
from core.incidents import claim_incident
from core.logging import get_logger
from core.loop import run_incident
from core.pricing import StaticPriceTable
from core.providers.simulated_executor import SimulatedExecutor
from core.repo.audit import append_entry
from core.tasks import app

log = get_logger(__name__)


@app.task(name="core.incident_tasks.process_incident")
def process_incident(incident_id: str, tenant_id: str) -> str:
    """Runs one incident through `run_incident` exactly once.

    Never raises: this task has no caller waiting on its result (`ml.tasks`
    fires it with `.delay()` and moves on), so an uncaught exception here
    would only ever surface as a worker-log crash nobody is watching. A
    failure is logged and written to `audit_log` instead.

    Returns a short status string (`"resolved"`, `"failed"`,
    `"already-claimed"`, or `"error"`) -- useful in tests and
    `celery ... --loglevel=INFO`, not a contract anything else depends on.
    """
    uid = UUID(incident_id)
    if not claim_incident(uid):
        log.info("incident %s already claimed or past OPEN; skipping", incident_id)
        return "already-claimed"

    try:
        final_state = asyncio.run(
            run_incident(
                uid,
                StaticPriceTable(),
                SimulatedExecutor(),
                QuorumConsensus(node_id="worker"),
            )
        )
    except Exception as exc:
        log.exception("run_incident failed for incident %s", incident_id)
        append_entry(
            actor="core.incident_tasks.process_incident",
            action="incident.processing_failed",
            payload={"incident_id": incident_id, "error": str(exc)},
            tenant_id=tenant_id,
        )
        return "error"

    return final_state.value
