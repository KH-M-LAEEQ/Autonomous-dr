"""Redis-backed "has this resource's detector fit yet" signal.

`ml.tasks.detect_anomalies` fits one `AnomalyDetector` per resource exactly
once, after `FIT_WINDOW_COUNT` windows of bootstrap history -- but that fit
happens inside the Celery worker/beat process, not the API process, so
nothing in the API's own memory can see it (same cross-process problem
`core/faults.py` solves for fault injection, and the same fix: Redis, which
already backs Celery per ADR-0006). The worker marks a resource fitted here
the moment its detector actually fits; `/ready` reads it back, which is how
`scripts/smoke.py`'s warm-up wait knows when to stop polling instead of
guessing a fixed sleep.
"""

from __future__ import annotations

import redis

from core.config import get_settings
from core.logging import get_logger

log = get_logger(__name__)

_KEY_PREFIX = "detector_fitted:"
_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def mark_fitted(resource_id: str) -> None:
    """No TTL -- once fit, a detector is never refit (`ml/tasks.py`), so
    this stays true until the worker restarts and loses its own in-memory
    `_fitted` set too."""
    _get_client().set(f"{_KEY_PREFIX}{resource_id}", "1")


def is_fitted(resource_id: str) -> bool:
    """False, never raises, if Redis is unreachable -- the same
    fail-safe-to-a-safe-default posture as `core.faults.get_fault`."""
    try:
        return bool(_get_client().exists(f"{_KEY_PREFIX}{resource_id}"))
    except redis.RedisError:
        log.warning("detector-fitted lookup failed for %s; redis unreachable", resource_id)
        return False


def clear_all_fitted() -> int:
    """Deletes every `detector_fitted:*` key. Called once, from `core.
    tasks`' `worker_ready` signal handler: a freshly started worker
    process has an empty in-memory `_fitted` set and `_history` dict
    (`ml/tasks.py`'s module-level state resets with the process), so any
    flag left over from a PREVIOUS worker process is stale -- it would
    tell `/ready` a resource is fitted when THIS worker hasn't fit
    anything yet, which is exactly backwards for a readiness signal.
    Returns the number of keys deleted (0 if Redis is unreachable, rather
    than raising -- a cleared cache that fails to clear just means the
    next warm-up wait takes a bit longer, not a worker that won't start).
    """
    try:
        client = _get_client()
        keys = list(client.scan_iter(match=f"{_KEY_PREFIX}*"))
        if keys:
            client.delete(*keys)
        return len(keys)
    except redis.RedisError:
        log.warning("clear_all_fitted failed; redis unreachable")
        return 0
