"""Celery application. The collector beat schedule lives here.

`include` loads task modules by string at worker startup rather than this
module importing them directly -- `core` must never import from `ml` (see
core/__init__.py), but the worker process still needs ml.tasks' detection
task registered. Celery's `include` is configuration, not a Python import
statement in core's source, so it doesn't violate the layering rule.
"""

from celery import Celery
from celery.schedules import crontab  # noqa: F401  -- used from Week 8

from core.config import get_settings

settings = get_settings()

app = Celery(
    "autonomousdr",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["core.tasks", "ml.tasks"],
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


@app.task(name="core.tasks.collect_telemetry")
def collect_telemetry() -> int:
    """One poll cycle across every enabled provider and active tenant.
    Returns the resource count polled (visible in `celery ... --loglevel=INFO`).
    """
    import asyncio

    from core.collector import poll_all_providers

    return asyncio.run(poll_all_providers())
