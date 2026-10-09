"""InfluxDB client helpers for the telemetry collector (Week 3 onwards).

The collector must run uninterrupted from Week 3. Treat any change in this file
as a change to your dataset.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from core.config import get_settings
from core.logging import get_logger
from core.models.domain import MetricWindow

log = get_logger(__name__)

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


def query_recent_window(resource_id: str, tenant_id: str, lookback_seconds: int) -> MetricWindow:
    """Builds a `MetricWindow` from the collector's last `lookback_seconds` of
    writes for one resource (Week 4, for the detector).

    Returns an empty-values window -- not an error -- if InfluxDB has nothing
    yet or is unreachable; callers must treat an empty window as "not enough
    data yet", never feed it to a detector as a reading of all-zeroes.

    `resource_id`/`tenant_id` are interpolated into the Flux query string
    because the influxdb-client Python API has no portable parameter binding
    for Flux; both always come from our own fixed resource list (see
    core/providers/simulated.py), never from a request body, so the quote
    check below is a belt-and-braces guard, not the actual trust boundary.
    """
    if '"' in resource_id or '"' in tenant_id:
        raise ValueError("resource_id/tenant_id must not contain a double quote")

    s = get_settings()
    now = datetime.now(UTC)
    start = now - timedelta(seconds=lookback_seconds)
    query = f"""
    from(bucket: "{s.influx_bucket}")
      |> range(start: {start.isoformat()}, stop: {now.isoformat()})
      |> filter(fn: (r) => r["_measurement"] == "telemetry")
      |> filter(fn: (r) => r["resource_id"] == "{resource_id}")
      |> filter(fn: (r) => r["tenant_id"] == "{tenant_id}")
    """

    values: dict[str, list[float]] = {}
    try:
        tables = get_client().query_api().query(query, org=s.influx_org)
        for table in tables:
            for record in table.records:
                signal = str(record.get_field())
                values.setdefault(signal, []).append(float(record.get_value()))
    except Exception:
        log.warning("query_recent_window failed for %s; influxdb unreachable", resource_id)

    return MetricWindow(
        resource_id=resource_id,
        tenant_id=tenant_id,
        start=start,
        end=now,
        step_seconds=10,
        values=values,
    )
