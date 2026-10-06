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
