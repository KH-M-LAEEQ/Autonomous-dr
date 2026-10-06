"""Incident lifecycle (Week 4): state machine + raw-SQL repo.

`IncidentState` transitions are validated, not assumed (enums.py). Week 4
only ever exercises OPEN -> nothing (detection creates an incident and stops
there); the rest of the machine exists now so Week 5's decision engine
(-> DECIDING -> ACTING) and later weeks (-> RESOLVED / FAILED) have a single
place that enforces which transitions are legal instead of each caller
trusting its own judgment.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from core.db import session_scope
from core.logging import get_logger
from core.models.enums import IncidentState

log = get_logger(__name__)

VALID_TRANSITIONS: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.OPEN: frozenset({IncidentState.DECIDING, IncidentState.FAILED}),
    IncidentState.DECIDING: frozenset({IncidentState.ACTING, IncidentState.FAILED}),
    IncidentState.ACTING: frozenset({IncidentState.RESOLVED, IncidentState.FAILED}),
    IncidentState.RESOLVED: frozenset(),
    IncidentState.FAILED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when code asks for a state change `VALID_TRANSITIONS` forbids."""


def check_transition(current: IncidentState, new: IncidentState) -> None:
    """Raises `InvalidTransition` if `current -> new` isn't in the table above."""
    if new not in VALID_TRANSITIONS[current]:
        raise InvalidTransition(f"{current.value} -> {new.value} is not a valid transition")


_FIND_OPEN = text(
    """
    SELECT id FROM incidents
    WHERE resource_id = :resource_id AND state NOT IN ('resolved', 'failed')
    ORDER BY opened_at DESC
    LIMIT 1
    """
)

_INSERT = text(
    """
    INSERT INTO incidents (tenant_id, resource_id, state, trigger_detection_id)
    VALUES (:tenant_id, :resource_id, 'open', :trigger_detection_id)
    RETURNING id
    """
)

_TRANSITION = text(
    """
    UPDATE incidents SET state = :new_state,
        closed_at = CASE WHEN :new_state IN ('resolved', 'failed') THEN now() ELSE closed_at END
    WHERE id = :incident_id
    """
)


def find_open_incident(resource_id: str) -> UUID | None:
    """The most recent not-yet-closed incident for a resource, if any.

    One open incident per resource at a time -- a second detection while one
    is already open must not create a duplicate, or the dashboard's incident
    feed fills with repeats of the same ongoing fault.
    """
    with session_scope() as session:
        row = session.execute(_FIND_OPEN, {"resource_id": resource_id}).first()
    return UUID(str(row[0])) if row else None


def open_incident(
    tenant_id: str, resource_id: str, trigger_detection_id: UUID | None = None
) -> UUID:
    """Creates a new incident in state OPEN. Caller's job to have already
    checked `find_open_incident` -- this never checks for you, so it stays a
    pure insert instead of an insert-or-return-existing with a race window.
    """
    with session_scope() as session:
        row = session.execute(
            _INSERT,
            {
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "trigger_detection_id": trigger_detection_id,
            },
        ).first()
    assert row is not None
    return UUID(str(row[0]))


def transition(incident_id: UUID, current: IncidentState, new: IncidentState) -> None:
    """Validates against `VALID_TRANSITIONS` before writing. `current` is
    supplied by the caller rather than re-read here, so the caller's own
    read-then-decide logic is what's authoritative about the starting state.
    """
    check_transition(current, new)
    with session_scope() as session:
        session.execute(_TRANSITION, {"incident_id": str(incident_id), "new_state": new.value})


_LIST = text(
    """
    SELECT id, tenant_id, resource_id, state, opened_at, closed_at, trigger_detection_id
    FROM incidents WHERE tenant_id = :tenant_id
    ORDER BY opened_at DESC LIMIT :limit
    """
)

_GET = text(
    """
    SELECT id, tenant_id, resource_id, state, opened_at, closed_at, trigger_detection_id
    FROM incidents WHERE id = :incident_id
    """
)


def list_incidents(tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(_LIST, {"tenant_id": tenant_id, "limit": limit}).all()
    return [dict(row._mapping) for row in rows]


def get_incident(incident_id: UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.execute(_GET, {"incident_id": str(incident_id)}).first()
    return dict(row._mapping) if row is not None else None
