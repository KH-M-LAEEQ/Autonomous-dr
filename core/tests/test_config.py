"""Safety tests for core/config.py.

`threshold_unscaled` (ml/detectors/threshold.py's `UnscaledThresholdDetector`)
exists only so the Week 4 scale-domination regression stays measurable in
`docs/results/practice-run.md` -- it must never be reachable from a running
system. `Settings.detector` and `Settings.node_detector` are the only two
config fields that select a detector by name (api/main.py logs `.detector`;
`ml/tasks.py`'s production detection loop hardcodes `build("threshold")`
directly rather than reading either field), so excluding it from both
`Literal`s is the entire enforcement mechanism. This file pins that.
"""

from __future__ import annotations

import typing

import pydantic
import pytest

from core.config import Settings


def test_threshold_unscaled_is_not_an_allowed_detector() -> None:
    allowed = typing.get_args(Settings.model_fields["detector"].annotation)
    assert "threshold_unscaled" not in allowed
    assert "threshold" in allowed


def test_threshold_unscaled_is_not_an_allowed_node_detector() -> None:
    allowed = typing.get_args(Settings.model_fields["node_detector"].annotation)
    assert "threshold_unscaled" not in allowed
    assert "threshold" in allowed


def test_setting_detector_to_threshold_unscaled_is_rejected() -> None:
    """Behavioural, not just a check of the declared type -- pydantic must
    actually refuse the value regardless of where it comes from (.env,
    environment variable, or a constructor kwarg)."""
    with pytest.raises(pydantic.ValidationError):
        Settings(detector="threshold_unscaled")  # type: ignore[arg-type]


def test_setting_node_detector_to_threshold_unscaled_is_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        Settings(node_detector="threshold_unscaled")  # type: ignore[arg-type]


def test_default_settings_never_select_threshold_unscaled() -> None:
    defaults = Settings()
    assert defaults.detector != "threshold_unscaled"
    assert defaults.node_detector != "threshold_unscaled"
