"""Tests for core/incident_tasks.py and core/incidents.claim_incident -- the
exactly-once guard behind the autonomous loop (ml.tasks.detect_anomalies
enqueues `process_incident`; nothing else should need to call `run_incident`
by hand). Needs a real Postgres, same reasoning as core/tests/test_loop.py.
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

from collections.abc import Callable
from uuid import UUID

import core.incident_tasks as incident_tasks_module
from core.incidents import claim_incident, get_incident, open_incident
from core.models.enums import IncidentState
from core.tests.conftest import MakeDbTenant, resource_id_for


def _open_incident_for(make_db_tenant: MakeDbTenant) -> tuple[str, UUID]:
    tenant_id = make_db_tenant()
    incident_id = open_incident(tenant_id, resource_id_for(tenant_id))
    return tenant_id, incident_id


def test_claim_incident_succeeds_once_then_fails(make_db_tenant: MakeDbTenant) -> None:
    _, incident_id = _open_incident_for(make_db_tenant)

    assert claim_incident(incident_id) is True
    incident = get_incident(incident_id)
    assert incident is not None
    assert incident["state"] == "deciding"

    # Second claim on the same (now non-OPEN) incident must fail -- this IS
    # the lock a retried/duplicated task delivery relies on.
    assert claim_incident(incident_id) is False
    unchanged = get_incident(incident_id)
    assert unchanged is not None
    assert unchanged["state"] == "deciding"  # unchanged, not re-claimed


def test_claim_incident_on_an_already_deciding_incident_fails_immediately(
    make_db_tenant: MakeDbTenant,
) -> None:
    _, incident_id = _open_incident_for(make_db_tenant)
    with session_scope() as session:
        session.execute(
            text("UPDATE incidents SET state = 'deciding' WHERE id = :i"), {"i": str(incident_id)}
        )
    assert claim_incident(incident_id) is False


def _patch_run_incident(
    monkeypatch: pytest.MonkeyPatch, result: IncidentState | Exception
) -> Callable[[], int]:
    """Replaces the `run_incident` name `core.incident_tasks` actually calls
    (its own module-level import, not `core.loop`'s) with a stub that either
    returns `result` or raises it, counting how many times it was awaited."""
    calls = {"n": 0}

    async def fake_run_incident(*args: object, **kwargs: object) -> IncidentState:
        calls["n"] += 1
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(incident_tasks_module, "run_incident", fake_run_incident)
    return lambda: calls["n"]


def test_process_incident_calls_run_incident_exactly_once_under_duplicate_delivery(
    make_db_tenant: MakeDbTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scenario this whole guard exists for: the same task message
    delivered twice (broker redelivery, a manual retry) must not run the
    loop twice for one incident."""
    tenant_id, incident_id = _open_incident_for(make_db_tenant)
    call_count = _patch_run_incident(monkeypatch, IncidentState.RESOLVED)

    first = incident_tasks_module.process_incident(str(incident_id), tenant_id)
    second = incident_tasks_module.process_incident(str(incident_id), tenant_id)

    assert first == "resolved"
    assert second == "already-claimed"
    assert call_count() == 1


def test_process_incident_logs_a_failure_to_audit_log_without_raising(
    make_db_tenant: MakeDbTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id, incident_id = _open_incident_for(make_db_tenant)
    _patch_run_incident(monkeypatch, RuntimeError("executor exploded"))

    result = incident_tasks_module.process_incident(str(incident_id), tenant_id)

    assert result == "error"  # did NOT raise -- a crash here must not take the worker down
    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT payload FROM audit_log WHERE action = 'incident.processing_failed' "
                "AND payload->>'incident_id' = :i ORDER BY id DESC LIMIT 1"
            ),
            {"i": str(incident_id)},
        ).first()
    assert row is not None
    assert "executor exploded" in row.payload["error"]
