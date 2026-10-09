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
from typing import Any

from core import influx
from core.config import get_settings
from core.detector_state import mark_fitted
from core.incident_tasks import process_incident
from core.incidents import find_open_incident, open_incident
from core.interfaces.anomaly_detector import AnomalyDetector
from core.logging import get_logger
from core.models.domain import Detection, MetricWindow
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


def _trace_tick(
    resource_id: str,
    window: MetricWindow,
    detector: AnomalyDetector,
    before: int | None,
    breached: bool,
) -> None:
    """DETECTOR_TRACE=1 only (core/config.py) -- never runs by default, never
    changes a decision. Logs exactly what `is_anomaly()` just saw: the raw
    tail of each signal's own value list (reveals out-of-order appends
    directly, which is the whole point -- see core/influx.py's
    query_recent_window), each signal's own residual and breach verdict
    recomputed independently here from the detector's fitted median/spread
    (duck-typed read via getattr, like score_batch/reset elsewhere in this
    codebase -- this never touches ml/detectors/threshold.py), and the
    consecutive-breach counter before and after. Live mode has no grace
    period, episode reset, or cooldown (those exist only in ml/harness/
    evaluate.py, for offline episode-labelled datasets) -- the ONLY way
    this counter changes is a breach or a non-breach on `is_anomaly()`,
    which is exactly what this line reports every tick.
    """
    median: dict[str, float] | None = getattr(detector, "_median", None)
    spread: dict[str, float] | None = getattr(detector, "_spread", None)
    fence = getattr(detector, "decision_threshold", None)
    per_signal: dict[str, dict[str, Any]] = {}
    if median is not None and spread is not None and fence is not None:
        for signal, series in window.values.items():
            if not series or signal not in median:
                continue
            latest = series[-1]
            residual = abs(latest - median[signal]) / spread[signal] if spread[signal] else 0.0
            per_signal[signal] = {
                "latest": round(latest, 2),
                "residual": round(residual, 3),
                "breach": residual > fence,
                "raw_tail": [round(v, 2) for v in series[-3:]],
            }
    explain = detector.explain()
    log.info(
        "DETECTOR_TRACE resource=%s window_end=%s fence=%s before=%s after=%s "
        "breach=%s winning_signal=%s per_signal=%s",
        resource_id,
        window.end.isoformat(),
        fence,
        before,
        explain.get("consecutive_breaches"),
        breached,
        explain.get("signal"),
        per_signal,
    )


async def _check_resource(resource_id: str, tenant_id: str) -> None:
    window = influx.query_recent_window(resource_id, tenant_id, LOOKBACK_SECONDS)
    if not window.values:
        return

    detector = _get_detector(resource_id)
    trace = get_settings().detector_trace

    if resource_id not in _fitted:
        history = _history.setdefault(resource_id, [])
        history.append(window)
        if trace:
            log.info(
                "DETECTOR_TRACE resource=%s window_end=%s bootstrapping=%d/%d",
                resource_id,
                window.end.isoformat(),
                len(history),
                FIT_WINDOW_COUNT,
            )
        if len(history) < FIT_WINDOW_COUNT:
            return  # still bootstrapping -- not enough history to fit yet
        detector.fit(history)
        _fitted.add(resource_id)
        mark_fitted(resource_id)  # cross-process signal -- see core/detector_state.py
        del _history[resource_id]  # history has done its job; don't hold it forever
        return  # the window that completed the fit isn't also scored

    before = getattr(detector, "_consecutive_breaches", None)
    breached = detector.is_anomaly(window)
    if trace:
        _trace_tick(resource_id, window, detector, before, breached)
    if not breached:
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
        # Autonomous from here: core.incident_tasks.process_incident runs
        # run_incident for this incident without anything else calling it.
        # Exactly-once is enforced there (claim_incident), not here -- this
        # is a fire-and-forget enqueue, not a guarantee of delivery.
        process_incident.delay(str(incident_id), tenant_id)


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
