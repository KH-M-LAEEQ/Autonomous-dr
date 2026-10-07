"""Reads against the `tenants` table."""

from sqlalchemy import text

from core.db import get_engine
from core.logging import get_logger

log = get_logger(__name__)


def list_active_tenant_ids() -> list[str]:
    """Every active tenant id, for jobs (the collector) that must iterate all
    of them. Returns `[]` rather than raising if Postgres is unreachable --
    a collector cycle that finds no tenants just does nothing this round,
    which is correct, not a crash."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text("SELECT id FROM tenants WHERE is_active ORDER BY id"))
            return [str(row[0]) for row in rows]
    except Exception:
        log.warning("list_active_tenant_ids failed; postgres unreachable", exc_info=True)
        return []


_GET_BUDGET = text("SELECT monthly_budget_usd FROM tenants WHERE id = :tenant_id")


def get_monthly_budget_usd(tenant_id: str) -> float:
    """The budget gate's cap (Week 5). Raises if the tenant row is missing --
    unlike `list_active_tenant_ids`, a missing cap is a data problem the
    caller must not silently treat as "unlimited"."""
    with get_engine().connect() as conn:
        row = conn.execute(_GET_BUDGET, {"tenant_id": tenant_id}).first()
    if row is None:
        raise ValueError(f"no tenant row for {tenant_id!r}")
    return float(row[0])
