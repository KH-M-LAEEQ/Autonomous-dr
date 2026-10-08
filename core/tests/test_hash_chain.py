"""Tests for core/audit/hash_chain.py."""

from __future__ import annotations

from typing import Any

from core.audit.hash_chain import GENESIS_HASH, compute_row_hash, verify_chain


def _build_chain(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    prev = GENESIS_HASH
    for payload in payloads:
        row_hash = compute_row_hash(payload, prev)
        rows.append({**payload, "prev_hash": prev, "hash": row_hash})
        prev = row_hash
    return rows


def test_valid_chain_verifies() -> None:
    rows = _build_chain([{"actor": "a", "action": "x"}, {"actor": "b", "action": "y"}])
    assert verify_chain(rows) == (True, None)


def test_empty_chain_verifies() -> None:
    assert verify_chain([]) == (True, None)


def test_tampered_payload_is_caught() -> None:
    rows = _build_chain([{"actor": "a", "action": "x"}, {"actor": "b", "action": "y"}])
    rows[1]["action"] = "tampered"
    assert verify_chain(rows) == (False, 1)


def test_tampered_hash_is_caught() -> None:
    rows = _build_chain([{"actor": "a", "action": "x"}])
    rows[0]["hash"] = "0" * 64
    assert verify_chain(rows) == (False, 0)


def test_wrong_genesis_prev_hash_is_caught() -> None:
    rows = _build_chain([{"actor": "a", "action": "x"}])
    rows[0]["prev_hash"] = "f" * 64
    assert verify_chain(rows) == (False, 0)


def test_a_valid_prefix_before_a_bad_row_still_reports_that_row() -> None:
    rows = _build_chain([{"actor": "a"}, {"actor": "b"}, {"actor": "c"}])
    rows[2]["actor"] = "tampered"
    assert verify_chain(rows) == (False, 2)


def test_compute_row_hash_is_deterministic_regardless_of_key_order() -> None:
    a = compute_row_hash({"x": 1, "y": 2}, GENESIS_HASH)
    b = compute_row_hash({"y": 2, "x": 1}, GENESIS_HASH)
    assert a == b


def test_compute_row_hash_changes_with_previous_hash() -> None:
    payload = {"x": 1}
    assert compute_row_hash(payload, GENESIS_HASH) != compute_row_hash(payload, "f" * 64)
