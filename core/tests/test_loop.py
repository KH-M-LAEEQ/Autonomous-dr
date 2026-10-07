"""End-to-end test for core/loop.py's run_incident: one real incident through
the whole Week 5 loop on SimulatedProvider.

Needs a real Postgres AND Redis (`core.faults` is Redis-backed in
production, and this test exercises the real API rather than monkeypatching
it, so the fault injection is as close to the real collector as this
simulator gets). Test database used: the same `adr` Postgres `make up` +
`make migrate` give you locally -- see core/tests/conftest.py's docstring
for why there is no separate test database. If Docker is off, both this and
every other Postgres-backed test in this file's sibling modules skip with a
clear message rather than failing on a confusing connection error.

**One simplification, named so it isn't mistaken for the real pipeline**:
getting a `Detection` here does not run a fitted `ml.detectors` model --
`core/` must never import from `ml/` (ml/tasks.py's own docstring), and a
full threshold-detector fit/bootstrap is what ml/tests already covers
exhaustively. This test instead builds the `Detection` directly from the
injected fault's `HealthReport`, the same shape `ml.tasks._check_resource`
would hand it, so the loop downstream of "a detection exists" is exercised
for real.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db import ping, session_scope

if not ping():
    pytest.skip(
        "Postgres is unreachable -- start it with `make up && make migrate`",
        allow_module_level=True,
    )

from datetime import UTC, datetime

from core import faults
from core.audit.hash_chain import verify_chain
from core.consensus.quorum import QuorumConsensus
from core.incidents import find_open_incident, get_incident, open_incident
from core.loop import run_incident
from core.models.domain import Detection
from core.models.enums import HealthState, IncidentState
from core.pricing import StaticPriceTable
from core.providers.simulated import SimulatedProvider, get_resource
from core.providers.simulated_executor import SimulatedExecutor
from core.repo.audit import list_for_verification
from core.repo.detections import insert_detection
from core.repo.resources import get_resource_record, upsert_resource

TENANT_ID = "tenant-a"
RESOURCE_ID = "sim-web-1"


def _cleanup(incident_id: object) -> None:
    """Deletes everything this test created, keyed off the one incident_id
    it made -- NEVER touches `audit_log` (deleting from a hash-chained table
    would invalidate every later row's chain) or the permanent `tenant-a`/
    `sim-web-1` rows this test reuses rather than owns."""
    with session_scope() as session:
        session.execute(
            text(
                "DELETE FROM votes WHERE proposal_id IN "
                "(SELECT id FROM proposals WHERE incident_id = :i)"
            ),
            {"i": str(incident_id)},
        )
        session.execute(
            text("DELETE FROM proposals WHERE incident_id = :i"), {"i": str(incident_id)}
        )
        session.execute(
            text("DELETE FROM decisions WHERE incident_id = :i"), {"i": str(incident_id)}
        )
        session.execute(
            text(
                "DELETE FROM cost_estimates WHERE action_id IN "
                "(SELECT id FROM actions WHERE incident_id = :i)"
            ),
            {"i": str(incident_id)},
        )
        session.execute(text("DELETE FROM actions WHERE incident_id = :i"), {"i": str(incident_id)})
        session.execute(
            text("DELETE FROM detections WHERE incident_id = :i"), {"i": str(incident_id)}
        )
        session.execute(text("DELETE FROM incidents WHERE id = :i"), {"i": str(incident_id)})


async def test_one_incident_through_the_whole_loop() -> None:
    resource = get_resource(RESOURCE_ID)
    assert resource is not None
    upsert_resource(resource)  # resources.id is an FK target for incidents/actions

    provider = SimulatedProvider()
    incident_id = None
    try:
        # -- fault -------------------------------------------------------
        provider.inject_fault(RESOURCE_ID, "cpu_hog", duration_seconds=120)
        health = await provider.get_health(RESOURCE_ID)
        assert health.state != HealthState.HEALTHY

        # -- detection (see module docstring for the simplification here) --
        detection = Detection(
            resource_id=RESOURCE_ID,
            tenant_id=TENANT_ID,
            detector="threshold",
            score=1.0,
            is_anomaly=True,
            detected_at=datetime.now(UTC),
            explanation={"state": health.state.value, "message": health.message},
        )
        insert_detection(detection)

        # -- incident ------------------------------------------------------
        assert find_open_incident(RESOURCE_ID) is None
        incident_id = open_incident(TENANT_ID, RESOURCE_ID, trigger_detection_id=detection.id)

        # -- the loop: decision -> cost gate -> consensus -> executor -------
        final_state = await run_incident(
            incident_id,
            StaticPriceTable(),
            SimulatedExecutor(),
            QuorumConsensus(node_id="node-a"),
        )

        assert final_state == IncidentState.RESOLVED
        incident = get_incident(incident_id)
        assert incident is not None
        assert incident["state"] == "resolved"
        assert incident["closed_at"] is not None

        with session_scope() as session:
            action_row = session.execute(
                text("SELECT id, status FROM actions WHERE incident_id = :i"),
                {"i": str(incident_id)},
            ).first()
            assert action_row is not None
            assert action_row.status == "succeeded"

            decision_row = session.execute(
                text("SELECT id, chosen_action_id FROM decisions WHERE incident_id = :i"),
                {"i": str(incident_id)},
            ).first()
            assert decision_row is not None
            assert str(decision_row.chosen_action_id) == str(action_row.id)

            cost_row = session.execute(
                text("SELECT action_id FROM cost_estimates WHERE action_id = :a"),
                {"a": str(action_row.id)},
            ).first()
            assert cost_row is not None

            proposal_row = session.execute(
                text("SELECT id, committed FROM proposals WHERE incident_id = :i"),
                {"i": str(incident_id)},
            ).first()
            assert proposal_row is not None
            assert proposal_row.committed is True

            vote_row = session.execute(
                text("SELECT voter_id, detection_id FROM votes WHERE proposal_id = :p"),
                {"p": str(proposal_row.id)},
            ).first()
            assert vote_row is not None
            assert str(vote_row.detection_id) == str(detection.id)

            detection_row = session.execute(
                text("SELECT id FROM detections WHERE id = :d"), {"d": str(detection.id)}
            ).first()
            assert detection_row is not None

        assert verify_chain(list_for_verification()) == (True, None)
    finally:
        faults.clear_fault(RESOURCE_ID)
        if incident_id is not None:
            _cleanup(incident_id)


async def test_resource_row_exists_for_the_fk_chain_to_work() -> None:
    """Sanity check on the test's own setup, not the loop: if this ever
    fails, every assertion above about FK-linked rows is unreliable."""
    resource = get_resource(RESOURCE_ID)
    assert resource is not None
    upsert_resource(resource)
    record = get_resource_record(RESOURCE_ID)
    assert record is not None
    assert record["tenant_id"] == TENANT_ID
