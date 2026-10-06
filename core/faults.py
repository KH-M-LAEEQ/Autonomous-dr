"""Redis-backed fault injection state (Week 3).

Faults are injected through the API process (`POST /api/v1/faults`) but must
be visible to the collector and detector tasks running in a separate Celery
worker/beat process -- in-memory state on the provider instance would not
cross that process boundary. Redis already backs Celery (ADR-0006), so it is
the shared store here too, and its key TTL does the expiry: "the fault ended"
is never a separate code path from "nobody cleaned it up".
"""

from __future__ import annotations

import redis

from core.config import get_settings
from core.logging import get_logger

log = get_logger(__name__)

_KEY_PREFIX = "fault:"
_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def set_fault(resource_id: str, fault_type: str, duration_seconds: int) -> None:
    """Active for exactly `duration_seconds` -- the Redis TTL expires it."""
    _get_client().set(f"{_KEY_PREFIX}{resource_id}", fault_type, ex=max(1, duration_seconds))


def get_fault(resource_id: str) -> str | None:
    """None if no fault is active, it already expired, or Redis is unreachable.

    A CloudProvider must never raise on transient failure (see
    core/interfaces/cloud_provider.py), so a Redis outage degrades to
    "treat every resource as healthy" rather than breaking health checks.
    """
    try:
        value = _get_client().get(f"{_KEY_PREFIX}{resource_id}")
    except redis.RedisError:
        log.warning("fault lookup failed for %s; redis unreachable", resource_id)
        return None
    return str(value) if value else None


def clear_fault(resource_id: str) -> None:
    _get_client().delete(f"{_KEY_PREFIX}{resource_id}")
