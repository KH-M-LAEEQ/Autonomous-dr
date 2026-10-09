"""InfluxDB client helpers for the telemetry collector (Week 3 onwards).

The collector must run uninterrupted from Week 3. Treat any change in this file
as a change to your dataset.
"""

from typing import Any

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from core.config import get_settings

_client: InfluxDBClient | None = None


def get_client() -> InfluxDBClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = InfluxDBClient(
            url=s.influx_url, token=s.influx_token, org=s.influx_org, timeout=2_000
        )
    return _client


def write_metrics(
    measurement: str,
    tags: dict[str, str],
    fields: dict[str, float],
    string_fields: dict[str, str] | None = None,
    timestamp: Any | None = None,
) -> None:
    """Write one point. Always tag with tenant_id, region and resource_id.

    `string_fields` is for descriptive, per-point values that are NOT a
    filterable dimension -- `health_state` (core/collector.py) is the
    reason this exists. A field, never a tag: every unique tag combination
    is its own InfluxDB series, so a value that changes on almost every
    write (health flips healthy -> degraded the instant a fault lands)
    fragments one resource's points across two series for as long as both
    straddle a query's time range. `query_recent_window`'s per-signal
    `series[-1]` ("the latest reading") then depends on which series the
    Flux client happens to iterate last -- not on which point is actually
    most recent. See that function's docstring for the full story; this is
    the write-side half of the fix.
    """
    s = get_settings()
    point = Point(measurement)
    for tag_key, tag_value in tags.items():
        point = point.tag(tag_key, tag_value)
    for field_key, field_value in fields.items():
        point = point.field(field_key, float(field_value))
    for string_field_key, string_field_value in (string_fields or {}).items():
        point = point.field(string_field_key, string_field_value)
    if timestamp is not None:
        point = point.time(timestamp)
    get_client().write_api(write_options=SYNCHRONOUS).write(bucket=s.influx_bucket, record=point)


def ping() -> bool:
    """True if InfluxDB answers. Used by /health."""
    try:
        return bool(get_client().ping())
    except Exception:
        return False
