"""Writes and reads against the `cost_estimates` table.

Week 5's budget gate (`core/budget.py`) reads `month_to_date_spend_usd`
*after* inserting the new estimate, so the just-written row is already
counted -- "save the estimate before the action runs" (PB-07) means before
the action, not before the gate decides whether the action may run.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from core.db import session_scope
from core.models.domain import CostEstimate

_INSERT = text(
    """
    INSERT INTO cost_estimates
        (action_id, tenant_id, currency, one_off_usd, hourly_usd,
         projected_monthly_usd, confidence, source, breakdown)
    VALUES
        (:action_id, :tenant_id, :currency, :one_off_usd, :hourly_usd,
         :projected_monthly_usd, :confidence, :source, CAST(:breakdown AS jsonb))
    """
)


def insert_cost_estimate(estimate: CostEstimate, tenant_id: str) -> None:
    """`tenant_id` is not on `CostEstimate` itself (it is 1:1 with an action,
    which already knows its tenant) -- the caller supplies it so this table's
    tenant-isolation column is always populated without the domain model
    needing a field that would just duplicate `Action.tenant_id`."""
    with session_scope() as session:
        session.execute(
            _INSERT,
            {
                "action_id": str(estimate.action_id),
                "tenant_id": tenant_id,
                "currency": estimate.currency,
                "one_off_usd": estimate.one_off_usd,
                "hourly_usd": estimate.hourly_usd,
                "projected_monthly_usd": estimate.projected_monthly_usd,
                "confidence": estimate.confidence,
                "source": estimate.source,
                "breakdown": json.dumps(estimate.breakdown),
            },
        )


_MONTH_TO_DATE_SPEND = text(
    """
    SELECT COALESCE(SUM(one_off_usd), 0)
    FROM cost_estimates
    WHERE tenant_id = :tenant_id
      AND created_at >= date_trunc('month', now())
    """
)


def month_to_date_spend_usd(tenant_id: str) -> float:
    """Sum of `one_off_usd` for every estimate recorded this calendar month
    for this tenant -- refused actions' estimates count too (PB-07 saves
    every estimate regardless of outcome), so a tenant that keeps proposing
    over-budget actions does not get a clean slate by having them rejected."""
    with session_scope() as session:
        row = session.execute(_MONTH_TO_DATE_SPEND, {"tenant_id": tenant_id}).first()
    assert row is not None
    return float(row[0])


_GET_BY_ACTION = text("SELECT * FROM cost_estimates WHERE action_id = :action_id")


def get_cost_estimate(action_id: UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(_GET_BY_ACTION, {"action_id": str(action_id)}).first()
    return dict(row._mapping) if row is not None else None
