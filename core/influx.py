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
        _client = InfluxDBClient(url=s.influx_url, token=s.influx_token, org=s.influx_org)
    return _client


def write_metrics(
    measurement: str,
    tags: dict[str, str],
    fields: dict[str, float],
    timestamp: Any | None = None,
) -> None:
    """Write one point. Always tag with tenant_id, region and resource_id."""
    s = get_settings()
    point = Point(measurement)
    for tag_key, tag_value in tags.items():
        point = point.tag(tag_key, tag_value)
    for field_key, field_value in fields.items():
        point = point.field(field_key, float(field_value))
    if timestamp is not None:
        point = point.time(timestamp)
    get_client().write_api(write_options=SYNCHRONOUS).write(bucket=s.influx_bucket, record=point)


def ping() -> bool:
    """True if InfluxDB answers. Used by /health."""
    try:
        return bool(get_client().ping())
    except Exception:
        return False
