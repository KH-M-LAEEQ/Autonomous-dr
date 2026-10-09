"""Writes and reads against the hash-chained `audit_log` table.

The hash covers tenant_id/actor/action/payload/created_at -- everything a
tampering attempt could change, not just the `payload` column -- which is
why `created_at` is generated here in application code and inserted
explicitly rather than left to the table's `server_default now()`: the hash
has to be computed from the exact value that ends up stored.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from core.audit.hash_chain import GENESIS_HASH, compute_row_hash
from core.db import session_scope

_LAST_HASH = text("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1")

_INSERT = text(
    """
    INSERT INTO audit_log (tenant_id, actor, action, payload, prev_hash, hash, created_at)
    VALUES (:tenant_id, :actor, :action, CAST(:payload AS jsonb), :prev_hash, :hash, :created_at)
    """
)

_LIST = text(
    """
    SELECT tenant_id, actor, action, payload, prev_hash, hash, created_at
    FROM audit_log ORDER BY id ASC
    """
)


def _hash_payload(
    tenant_id: str | None, actor: str, action: str, payload: dict[str, Any], created_at: datetime
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "actor": actor,
        "action": action,
        "payload": payload,
        "created_at": created_at.isoformat(),
    }


def append_entry(
    actor: str, action: str, payload: dict[str, Any], tenant_id: str | None = None
) -> str:
    """Appends one row, chaining off the current last row's hash. Returns the
    new row's hash.

    Not safe against concurrent writers racing on the same chain tail --
    Week 4's only writer is the detection task; a multi-writer audit log
    needs a DB-level lock on the tail read, not a bigger hash function.
    """
    created_at = datetime.now(UTC)
    with session_scope() as session:
        last = session.execute(_LAST_HASH).first()
        prev_hash = str(last[0]) if last else GENESIS_HASH
        row_hash = compute_row_hash(
            _hash_payload(tenant_id, actor, action, payload, created_at), prev_hash
        )
        session.execute(
            _INSERT,
            {
                "tenant_id": tenant_id,
                "actor": actor,
                "action": action,
                "payload": json.dumps(payload),
                "prev_hash": prev_hash,
                "hash": row_hash,
                "created_at": created_at,
            },
        )
    return row_hash


def list_for_verification() -> list[dict[str, Any]]:
    """Every row, oldest first, in exactly the shape `hash_chain.verify_chain`
    expects: the fields that were hashed at insert time, plus `prev_hash`/`hash`.
    """
    with session_scope() as session:
        rows = session.execute(_LIST).all()
    entries = []
    for row in rows:
        m = row._mapping
        hashed = _hash_payload(
            m["tenant_id"], m["actor"], m["action"], m["payload"], m["created_at"]
        )
        entries.append({**hashed, "prev_hash": m["prev_hash"], "hash": m["hash"]})
    return entries
