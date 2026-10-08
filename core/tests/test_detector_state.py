"""Tests for core/detector_state.py and core.tasks' worker_ready handler
that clears it. Needs a real Redis -- skips module-wide if unreachable,
same idiom as core/tests/conftest.py's Postgres skip.
"""

from __future__ import annotations

import redis as redis_module

import core.detector_state as detector_state_module
from core.config import get_settings

try:
    redis_module.Redis.from_url(get_settings().redis_url).ping()
    _REDIS_UP = True
except redis_module.RedisError:
    _REDIS_UP = False

import pytest

if not _REDIS_UP:
    pytest.skip("Redis is unreachable -- start it with `make up`", allow_module_level=True)

from uuid import uuid4

import core.tasks as tasks_module
from core.detector_state import clear_all_fitted, is_fitted, mark_fitted


def _fresh_resource_id() -> str:
    return f"test-resource-{uuid4().hex[:10]}"


def test_clear_all_fitted_clears_marked_resources() -> None:
    a, b = _fresh_resource_id(), _fresh_resource_id()
    mark_fitted(a)
    mark_fitted(b)
    assert is_fitted(a) is True
    assert is_fitted(b) is True

    cleared = clear_all_fitted()

    assert cleared >= 2
    assert is_fitted(a) is False
    assert is_fitted(b) is False


def test_clear_all_fitted_does_not_touch_unrelated_keys() -> None:
    client = detector_state_module._get_client()
    unrelated_key = f"fault:{uuid4().hex[:10]}"  # core.faults' own key prefix
    client.set(unrelated_key, "cpu_hog", ex=60)
    try:
        clear_all_fitted()
        assert client.get(unrelated_key) == "cpu_hog"
    finally:
        client.delete(unrelated_key)


def test_worker_ready_signal_clears_a_stale_fitted_flag() -> None:
    """The actual requirement: firing the real Celery worker_ready signal
    -- not just calling the clear function directly -- must trigger the
    clear. This is what proves the handler is actually wired up in
    core/tasks.py, not just that clear_all_fitted works in isolation."""
    resource_id = _fresh_resource_id()
    mark_fitted(resource_id)
    assert is_fitted(resource_id) is True

    tasks_module.worker_ready.send(sender=None)

    assert is_fitted(resource_id) is False
