"""Shared fixtures for the Week 5 loop tests, which need a real Postgres.

Test database used: the same Postgres `make up` + `make migrate` give you
locally (`adr` on localhost:5432) -- there is no separate `adr_test`
database. Isolation instead comes from `make_db_tenant`: every test gets its
own throwaway tenant id (and a matching resource row), so nothing here ever
touches the two seeded demo tenants (`tenant-a`/`tenant-b`) or leaks state
between test runs or between test files. Teardown wipes every FK-scoped
child row it created EXCEPT audit_log (and, because of audit_log's FK, the
tenant row itself) -- see `_TENANT_SCOPED_TABLES`'s comment for why. Any
test file that needs Postgres checks `core.db.ping()` itself at
module level (`pytest.skip(..., allow_module_level=True)`, the same idiom
`ml/tests/test_iforest_detector.py` uses for its own optional dependency) so
the DB-free majority of the suite is unaffected when Postgres is down.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import text

from core.db import session_scope

# Deleted in reverse FK-dependency order. `tenant_id` lives directly on every
# one of these tables (ADR/migration convention), so one filter per table is
# enough -- no joins needed to find what belongs to a throwaway tenant.
#
# audit_log is deliberately NOT in this list. It is hash-chained and global
# across every tenant (each row's prev_hash points at whatever row -- any
# tenant's -- was last at insert time), so deleting even one throwaway
# tenant's own rows from it breaks verify_chain() for every row inserted
# after it, for every tenant, the moment anything else (a live Celery
# worker's own audit writes included -- see core/incident_tasks.py) has
# written a row since. core/tests/test_loop.py's _cleanup() already
# follows this rule for the same reason; this fixture used to be the one
# place that didn't. Because audit_log.tenant_id has an FK to tenants.id,
# this also means the tenant row itself can't be deleted either -- left
# behind on purpose, small and harmless, same as the audit rows pointing
# at it.
_TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "votes",
    "proposals",
    "decisions",
    "cost_estimates",
    "actions",
    "detections",
    "incidents",
    "resources",
)


def _wipe(tenant_id: str) -> None:
    with session_scope() as session:
        for table in _TENANT_SCOPED_TABLES:
            session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            )


def resource_id_for(tenant_id: str) -> str:
    """Deterministic from the tenant id, so a test that only has the tenant
    id (most of them) can still address its one resource row."""
    return f"{tenant_id}-resource"


#: What `make_db_tenant` resolves to: call it with a budget, get a tenant id.
MakeDbTenant = Callable[..., str]


@pytest.fixture
def make_db_tenant() -> Iterator[MakeDbTenant]:
    """Factory fixture: `make_db_tenant(budget_usd=...)` returns a fresh
    tenant id backed by a real row (plus one resource row, since every
    FK chain in this schema -- actions, incidents -- bottoms out at
    `resources`). Every tenant it creates is wiped on teardown regardless of
    how the test ends."""
    created: list[str] = []

    def _make(budget_usd: float = 25.0) -> str:
        tenant_id = f"tenant-test-{uuid4().hex[:10]}"
        with session_scope() as session:
            session.execute(
                text(
                    "INSERT INTO tenants (id, name, monthly_budget_usd) "
                    "VALUES (:id, :name, :budget)"
                ),
                {"id": tenant_id, "name": f"test tenant {tenant_id}", "budget": budget_usd},
            )
            session.execute(
                text(
                    "INSERT INTO resources (id, tenant_id, provider, region, kind, name) "
                    "VALUES (:id, :tenant_id, 'simulated', 'sim-us-east-1', 'web_service', :id)"
                ),
                {"id": resource_id_for(tenant_id), "tenant_id": tenant_id},
            )
        created.append(tenant_id)
        return tenant_id

    yield _make

    for tenant_id in created:
        _wipe(tenant_id)
