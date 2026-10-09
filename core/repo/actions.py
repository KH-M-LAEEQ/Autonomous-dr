"""Writes and reads against the `actions` table."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from core.db import session_scope
from core.models.domain import Action
from core.models.enums import ActionStatus

_INSERT = text(
    """
    INSERT INTO actions
        (id, tenant_id, incident_id, provider, type, tier, target_resource_id,
         params, status)
    VALUES
        (:id, :tenant_id, :incident_id, :provider, :type, :tier, :target_resource_id,
         CAST(:params AS jsonb), :status)
    """
)


def insert_action(action: Action) -> None:
    with session_scope() as session:
        session.execute(
            _INSERT,
            {
                "id": str(action.id),
                "tenant_id": action.tenant_id,
                "incident_id": str(action.incident_id) if action.incident_id else None,
                "provider": action.provider.value,
                "type": action.type.value,
                "tier": action.tier.value,
                "target_resource_id": action.target_resource_id,
                "params": json.dumps(action.params),
                "status": action.status.value,
            },
        )


_UPDATE_STATUS = text(
    """
    UPDATE actions SET
        status = :status,
        provider_ref = COALESCE(:provider_ref, provider_ref),
        rollback_token = COALESCE(:rollback_token, rollback_token),
        actual_cost_usd = COALESCE(:actual_cost_usd, actual_cost_usd),
        error = COALESCE(:error, error),
        started_at = COALESCE(:started_at, started_at),
        finished_at = COALESCE(:finished_at, finished_at)
    WHERE id = :action_id
    """
)


def update_action_status(
    action_id: UUID,
    status: ActionStatus,
    *,
    provider_ref: str | None = None,
    rollback_token: str | None = None,
    actual_cost_usd: float | None = None,
    error: str | None = None,
    started_at: object | None = None,
    finished_at: object | None = None,
) -> None:
    with session_scope() as session:
        session.execute(
            _UPDATE_STATUS,
            {
                "action_id": str(action_id),
                "status": status.value,
                "provider_ref": provider_ref,
                "rollback_token": rollback_token,
                "actual_cost_usd": actual_cost_usd,
                "error": error,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )


_GET = text("SELECT * FROM actions WHERE id = :action_id")


def get_action(action_id: UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(_GET, {"action_id": str(action_id)}).first()
    return dict(row._mapping) if row is not None else None
