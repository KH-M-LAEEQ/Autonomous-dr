"""Writes against the `resources` table.

The collector is the only writer: every poll cycle upserts the resource
metadata it just saw, which is what keeps `resources.id` valid as an FK
target for `incidents.resource_id` / `detections.resource_id` without a
separate "register this resource" step anywhere else.
"""

import json
from typing import Any

from sqlalchemy import text

from core.db import session_scope
from core.logging import get_logger
from core.models.domain import Resource

log = get_logger(__name__)

_UPSERT = text(
    """
    INSERT INTO resources (id, provider, region, tenant_id, kind, name, metadata, updated_at)
    VALUES (:id, :provider, :region, :tenant_id, :kind, :name, CAST(:metadata AS jsonb), now())
    ON CONFLICT (id) DO UPDATE SET
        provider = EXCLUDED.provider,
        region = EXCLUDED.region,
        tenant_id = EXCLUDED.tenant_id,
        kind = EXCLUDED.kind,
        name = EXCLUDED.name,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
)


def upsert_resource(resource: Resource) -> None:
    """Best-effort: a Postgres outage must not stop the collector from
    writing telemetry to InfluxDB, so failures here are logged, not raised."""
    try:
        with session_scope() as session:
            session.execute(
                _UPSERT,
                {
                    "id": resource.id,
                    "provider": resource.provider.value,
                    "region": resource.region,
                    "tenant_id": resource.tenant_id,
                    "kind": resource.kind,
                    "name": resource.name,
                    "metadata": json.dumps(resource.metadata),
                },
            )
    except Exception:
        log.warning(
            "upsert_resource failed for %s; postgres unreachable", resource.id, exc_info=True
        )


_GET = text("SELECT * FROM resources WHERE id = :resource_id")


def get_resource_record(resource_id: str) -> dict[str, Any] | None:
    """Raw row, region included -- the decision engine needs the region to
    price a candidate action; nothing here needs the full `Resource` model."""
    with session_scope() as session:
        row = session.execute(_GET, {"resource_id": resource_id}).first()
    return dict(row._mapping) if row is not None else None
