"""Celery application. The collector beat schedule lives here.

`include` loads task modules by string at worker startup rather than this
module importing them directly -- `core` must never import from `ml` (see
core/__init__.py), but the worker process still needs ml.tasks' detection
task registered. Celery's `include` is configuration, not a Python import
statement in core's source, so it doesn't violate the layering rule.
"""

from celery import Celery
from celery.schedules import crontab  # noqa: F401  -- used from Week 8
from celery.signals import worker_ready

from core.config import get_settings
from core.logging import get_logger

settings = get_settings()
log = get_logger(__name__)

app = Celery(
    "autonomousdr",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["core.tasks", "core.incident_tasks", "ml.tasks"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Karachi",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    beat_schedule={
        "collect-telemetry": {"task": "core.tasks.collect_telemetry", "schedule": 10.0},
        "detect-anomalies": {"task": "ml.tasks.detect_anomalies", "schedule": 10.0},
    },
)


@worker_ready.connect
def _clear_stale_fitted_flags(**kwargs: object) -> None:
    """A fresh worker process's `ml.tasks._fitted` set starts empty, so any
    `detector_fitted:*` Redis key surviving from a PREVIOUS worker process
    is stale -- see `core.detector_state.clear_all_fitted`'s docstring.
    Runs once, right after this worker finishes booting, before it starts
    pulling tasks off the queue.
    """
    cleared = _clear_stale_fitted_flags_impl()
    log.info("cleared %d stale detector-fitted flag(s) on worker start", cleared)


def _clear_stale_fitted_flags_impl() -> int:
    """Split from the signal handler so a test can call this directly
    without sending a real Celery signal."""
    from core.detector_state import clear_all_fitted

    return clear_all_fitted()


@app.task(name="core.tasks.collect_telemetry")
def collect_telemetry() -> int:
    """One poll cycle across every enabled provider and active tenant.
    Returns the resource count polled (visible in `celery ... --loglevel=INFO`).
    """
    import asyncio

    from core.collector import poll_all_providers

    return asyncio.run(poll_all_providers())
