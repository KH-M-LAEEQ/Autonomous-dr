"""Writes and reads against the `decisions` table.

`chosen_action_id` has a FK to `actions.id` -- the caller must have already
inserted that action (`core.repo.actions.insert_action`) before calling
`insert_decision`, or Postgres rejects the insert. Only the chosen action
gets a row in `actions`; the options that lost are recorded as plain dicts
inside `decision.rejected` (JSONB), not as rows of their own -- they were
never going to run.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from core.db import session_scope
from core.models.domain import Decision

_INSERT = text(
    """
    INSERT INTO decisions
        (id, tenant_id, incident_id, chosen_action_id, utility, terms, weights,
         formula_version, rejected, rationale)
    VALUES
        (:id, :tenant_id, :incident_id, :chosen_action_id, :utility,
         CAST(:terms AS jsonb), CAST(:weights AS jsonb), :formula_version,
         CAST(:rejected AS jsonb), :rationale)
    """
)


def insert_decision(decision: Decision, tenant_id: str) -> None:
    with session_scope() as session:
        session.execute(
            _INSERT,
            {
                "id": str(decision.id),
                "tenant_id": tenant_id,
                "incident_id": str(decision.incident_id),
                "chosen_action_id": (
                    str(decision.chosen_action.id) if decision.chosen_action else None
                ),
                "utility": decision.utility,
                "terms": json.dumps(decision.terms),
                "weights": json.dumps(decision.weights),
                "formula_version": decision.formula_version,
                "rejected": json.dumps(decision.rejected),
                "rationale": decision.rationale,
            },
        )


_GET = text("SELECT * FROM decisions WHERE id = :decision_id")


def get_decision_record(decision_id: UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(_GET, {"decision_id": str(decision_id)}).first()
    return dict(row._mapping) if row is not None else None
