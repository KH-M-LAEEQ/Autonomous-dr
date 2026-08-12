"""Hash-chained audit log helpers. Week 4 owns the implementation.

Deliberately left as signatures: writing this is a 2-hour task and it is the
BACKEND role's Week 4 deliverable. The signatures are here so Week 4 does not
start with a naming argument.
"""

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

    Week 29 demos this live by tampering with one row. Keep it fast enough to
    run over the whole table on stage.
    """
    raise NotImplementedError("Week 4 -- BACKEND")
