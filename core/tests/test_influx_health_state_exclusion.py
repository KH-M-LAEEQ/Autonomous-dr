"""Lock in that `health_state` never reaches a `MetricWindow`.

Every reader of InfluxDB in this repo goes through one of two functions:
`core.influx.query_recent_window` (ml/tasks.py, scripts/smoke.py's
`check_collector`) or `core.influx.ping` (api/routers/health.py,
scripts/verify.py's HTTP ping -- neither touches field data at all). There
is no second, independent read path that queries InfluxDB directly, so the
single Flux-level exclusion in `query_recent_window` (b0241b7) is the only
place `health_state` needs to be kept out of a signal series -- this test
is what keeps that true if the query is ever edited.

No live InfluxDB: `get_client` is monkeypatched to a fake client that
records the Flux query text instead of running it.
"""

from __future__ import annotations

import pytest

import core.influx as influx_module


class _CapturingQueryApi:
    def __init__(self, captured: dict[str, str]) -> None:
        self._captured = captured

    def query(self, query: str, org: str) -> list:
        self._captured["query"] = query
        return []


class _CapturingClient:
    def __init__(self, captured: dict[str, str]) -> None:
        self._captured = captured

    def query_api(self) -> _CapturingQueryApi:
        return _CapturingQueryApi(self._captured)


def test_query_recent_window_excludes_health_state_at_the_flux_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setattr(influx_module, "get_client", lambda: _CapturingClient(captured))

    window = influx_module.query_recent_window("r1", "tenant-a", lookback_seconds=120)

    assert 'r["_field"] != "health_state"' in captured["query"]
    assert "health_state" not in window.values
