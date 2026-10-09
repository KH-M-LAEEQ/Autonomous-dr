"""Detector registry. Every detector self-registers so config can name it.

Week 4 adds threshold, Week 10 adds iforest + the PyOD family, Week 11 adds lstm
and ensemble, Week 14 adds gnn. The registry means adding one is a single line.
"""

import contextlib

from core.interfaces import AnomalyDetector

REGISTRY: dict[str, type[AnomalyDetector]] = {}


def register(name: str):  # type: ignore[no-untyped-def]
    def decorator(cls: type[AnomalyDetector]) -> type[AnomalyDetector]:
        REGISTRY[name] = cls
        return cls

    return decorator


def build(name: str, **kwargs: object) -> AnomalyDetector:
    if name not in REGISTRY:
        raise KeyError(f"unknown detector {name!r}; registered: {sorted(REGISTRY)}")
    return REGISTRY[name](**kwargs)  # type: ignore[call-arg, arg-type]


# Imported for its @register("threshold") side effect, after REGISTRY/register
# exist above -- threshold.py imports `register` back from this module.
from ml.detectors import threshold  # noqa: E402, F401

# Same, for @register("iforest") -- but guarded, because iforest.py needs
# numpy and scikit-learn from the `ml` extra (pyproject.toml) and this module
# is imported by ml/tasks.py, which the BACKEND role's Celery worker loads via
# core.tasks' `include` list. Without the guard, a worker running without the
# ml extra fails at import instead of simply not offering this detector.
# The failure stays legible either way: build("iforest") raises
# `unknown detector 'iforest'; registered: ['threshold']`.
with contextlib.suppress(ModuleNotFoundError):
    from ml.detectors import iforest  # noqa: F401
