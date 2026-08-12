"""Celery application. The collector beat schedule lives here.

Week 3 replaces the placeholder task with the real 10-second collector poll.
"""

from celery import Celery
from celery.schedules import crontab  # noqa: F401  -- used from Week 8

from core.config import get_settings

settings = get_settings()

app = Celery("autonomousdr", broker=settings.redis_url, backend=settings.redis_url)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Karachi",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    beat_schedule={
        # Week 3: swap this for collector.poll_all_providers
        "heartbeat": {"task": "core.tasks.heartbeat", "schedule": 10.0},
    },
)


@app.task(name="core.tasks.heartbeat")
def heartbeat() -> str:
    """Proves beat -> broker -> worker works end to end. Delete in Week 3."""
    return "ok"
