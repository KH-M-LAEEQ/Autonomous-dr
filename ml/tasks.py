"""Detection orchestration (Week 4).

Runs every 10s via `core.tasks`' beat schedule, right alongside the
collector. Lives in `ml`, not `core`, because it calls `ml.detectors.build` --
`core` must never import from `ml` (core/__init__.py) -- and is registered
onto the shared Celery app via `core.tasks.app`'s `include` list rather than
`core.tasks` importing this module.

One `AnomalyDetector` instance per resource, per the interface's contract
(a shared instance would corrupt the consecutive-breach counter across
resources). Each is fit exactly once, after `FIT_WINDOW_COUNT` windows of
bootstrap history -- never refit afterwards, so a later fault can't drag the
baseline up to absorb itself. That also means a fault injected during the
bootstrap window (the first ~5 minutes after a resource is first seen) can
corrupt the baseline; in practice the collector has been running far longer
than that by the time anyone reaches for the fault button.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from core import influx
from core.detector_state import mark_fitted
from core.incidents import find_open_incident, open_incident
from core.interfaces.anomaly_detector import AnomalyDetector
from core.logging import get_logger
from core.models.domain import Detection
from core.providers import enabled_providers
from core.repo.audit import append_entry
from core.repo.detections import insert_detection
from core.repo.tenants import list_active_tenant_ids
from core.tasks import app
from ml.detectors import build

log = get_logger(__name__)

LOOKBACK_SECONDS = 120  # 12 points at the collector's 10s interval
FIT_WINDOW_COUNT = 30  # ~5 minutes of bootstrap history before the baseline is fit

_detectors: dict[str, AnomalyDetector] = {}
_history: dict[str, list] = {}  # type: ignore[type-arg]
_fitted: set[str] = set()


def _get_detector(resource_id: str) -> AnomalyDetector:
    if resource_id not in _detectors:
        _detectors[resource_id] = build("threshold")
    return _detectors[resource_id]


async def _check_resource(resource_id: str, tenant_id: str) -> None:
    window = influx.query_recent_window(resource_id, tenant_id, LOOKBACK_SECONDS)
    if not window.values:
        return

    detector = _get_detector(resource_id)

    if resource_id not in _fitted:
        history = _history.setdefault(resource_id, [])
        history.append(window)
        if len(history) < FIT_WINDOW_COUNT:
            return  # still bootstrapping -- not enough history to fit yet
        detector.fit(history)
        _fitted.add(resource_id)
        mark_fitted(resource_id)  # cross-process signal -- see core/detector_state.py
        del _history[resource_id]  # history has done its job; don't hold it forever
        return  # the window that completed the fit isn't also scored

    if not detector.is_anomaly(window):
        return

    detection = Detection(
        resource_id=resource_id,
        tenant_id=tenant_id,
        detector=detector.name,
        score=detector.score(window),
        is_anomaly=True,
        detected_at=datetime.now(UTC),
        explanation=detector.explain(),
    )
    insert_detection(detection)
    append_entry(
        actor="ml.tasks.detect_anomalies",
        action="detection.created",
        payload=detection.model_dump(mode="json"),
        tenant_id=tenant_id,
    )

    if find_open_incident(resource_id) is None:
        incident_id = open_incident(tenant_id, resource_id, trigger_detection_id=detection.id)
        log.info("incident %s opened for resource %s", incident_id, resource_id)
        append_entry(
            actor="ml.tasks.detect_anomalies",
            action="incident.opened",
            payload={"incident_id": str(incident_id), "resource_id": resource_id},
            tenant_id=tenant_id,
        )


async def _run() -> int:
    count = 0
    for provider in enabled_providers():
        for tenant_id in list_active_tenant_ids():
            for resource in await provider.list_resources(tenant_id):
                await _check_resource(resource.id, tenant_id)
                count += 1
    return count


@app.task(name="ml.tasks.detect_anomalies")
def detect_anomalies() -> int:
    """One detection cycle across every enabled provider and active tenant."""
    return asyncio.run(_run())
