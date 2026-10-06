"""Hash-chained audit log helpers (Week 4)."""

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def compute_row_hash(payload: dict[str, Any], previous_hash: str) -> str:
    """SHA-256 over the canonical JSON of the payload plus the previous row hash.

    Canonicalisation matters: sort keys, no whitespace, UTF-8. If two machines
    serialise the same row differently, your chain verification fails for no
    reason and you will lose an evening to it.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{previous_hash}{canonical}".encode()).hexdigest()


def verify_chain(rows: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Re-derive every hash. Returns (ok, index_of_first_bad_row).

    `rows` must be in insertion order and each dict must carry `prev_hash`
    and `hash` alongside whatever payload fields `compute_row_hash` was
    originally given -- the caller is responsible for excluding `prev_hash`
    and `hash` themselves from the payload passed to `compute_row_hash`, or
    every row would need to hash its own hash.

    Week 29 demos this live by tampering with one row. Keep it fast enough to
    run over the whole table on stage.
    """
    expected_previous = GENESIS_HASH
    for index, row in enumerate(rows):
        payload = {k: v for k, v in row.items() if k not in ("prev_hash", "hash")}
        if row.get("prev_hash") != expected_previous:
            return False, index
        if compute_row_hash(payload, expected_previous) != row.get("hash"):
            return False, index
        expected_previous = str(row["hash"])
    return True, None
