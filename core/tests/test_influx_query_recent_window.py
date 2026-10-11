"""Regression test for core/influx.py::query_recent_window, specifically
the stale-latest-reading bug fixed in b0241b7 ("health_state as an InfluxDB
tag fragmented a resource's series across the fault boundary").

No live InfluxDB needed or used -- `get_client` is monkeypatched to a fake
client whose `query_api().query(...)` returns fake Flux tables/records built
by hand, mirroring exactly the shape `query_recent_window` consumes
(`for table in tables: for record in table.records`, `record.get_field()`,
`record.get_time()`, `record.get_value()`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import core.influx as influx_module


class _FakeRecord:
    def __init__(self, field: str, time: datetime, value: float) -> None:
        self._field = field
        self._time = time
        self._value = value

    def get_field(self) -> str:
        return self._field

    def get_time(self) -> datetime:
        return self._time

    def get_value(self) -> float:
        return self._value


class _FakeTable:
    def __init__(self, records: list[_FakeRecord]) -> None:
        self.records = records


class _FakeQueryApi:
    def __init__(self, tables: list[_FakeTable]) -> None:
        self._tables = tables

    def query(self, query: str, org: str) -> list[_FakeTable]:
        return self._tables


class _FakeClient:
    def __init__(self, tables: list[_FakeTable]) -> None:
        self._tables = tables

    def query_api(self) -> _FakeQueryApi:
        return _FakeQueryApi(self._tables)


def test_query_recent_window_returns_the_chronologically_latest_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact b0241b7 scenario: a stale, pre-fault point sits alone in a
    Flux table (its own tag set) that the client happens to iterate LAST;
    the real, breach-worthy post-fault readings sit in a table iterated
    FIRST. `values[signal][-1]` ("the latest reading", trusted by
    ml/detectors/threshold.py's `_last_values`) must be the chronologically
    latest point regardless of which table arrived last."""
    now = datetime.now(UTC)
    stale_table = _FakeTable([_FakeRecord("cpu_percent", now - timedelta(seconds=100), 12.0)])
    fresh_table = _FakeTable(
        [
            _FakeRecord("cpu_percent", now - timedelta(seconds=20), 55.0),
            _FakeRecord("cpu_percent", now - timedelta(seconds=10), 97.0),
        ]
    )
    # Fresh table iterated first, stale table iterated last -- the exact
    # ordering that made `series[-1]` wrong before the fix.
    tables = [fresh_table, stale_table]
    monkeypatch.setattr(influx_module, "get_client", lambda: _FakeClient(tables))

    window = influx_module.query_recent_window("r1", "tenant-a", lookback_seconds=120)

    assert window.values["cpu_percent"] == [12.0, 55.0, 97.0]
    assert window.values["cpu_percent"][-1] == 97.0
