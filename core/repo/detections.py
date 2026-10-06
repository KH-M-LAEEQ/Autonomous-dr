"""Writes against the `detections` table."""

import json

from sqlalchemy import text

from core.db import session_scope
from core.models.domain import Detection

_INSERT = text(
    """
    INSERT INTO detections
        (id, resource_id, tenant_id, detector, score, is_anomaly, detected_at,
         model_version, explanation)
    VALUES
        (:id, :resource_id, :tenant_id, :detector, :score, :is_anomaly, :detected_at,
         :model_version, :explanation::jsonb)
    """
)


def insert_detection(detection: Detection) -> None:
    with session_scope() as session:
        session.execute(
            _INSERT,
            {
                "id": str(detection.id),
                "resource_id": detection.resource_id,
                "tenant_id": detection.tenant_id,
                "detector": detection.detector,
                "score": detection.score,
                "is_anomaly": detection.is_anomaly,
                "detected_at": detection.detected_at,
                "model_version": detection.model_version,
                "explanation": json.dumps(detection.explanation),
            },
        )
