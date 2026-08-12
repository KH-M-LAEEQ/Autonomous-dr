"""Detectors, evaluation harness, dataset tooling. Owned by the AI role.

`ml` may import from `core`. `core` must never import from `ml` -- the runtime
loads detectors through the AnomalyDetector interface via config.
"""
