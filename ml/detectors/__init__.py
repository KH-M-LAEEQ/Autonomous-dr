"""Detector registry. Every detector self-registers so config can name it.

Week 4 adds threshold, Week 10 adds iforest + the PyOD family, Week 11 adds lstm
and ensemble, Week 14 adds gnn. The registry means adding one is a single line.
"""

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
