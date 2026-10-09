"""Tests for ml/datasets/make_episodes.py's shape scheduling.

Shapes used to be drawn independently per episode (`rng.choice`), which can
and did cluster a shape into one part of the timeline (see the module
docstring in make_episodes.py for the v4 `--seed 42` numbers). These tests
pin the round-robin-per-virtual-day replacement: round robin across days
means every shape recurs steadily end to end; shuffled within a day means
the ROTATION order is randomised rather than a fixed day-after-day pattern.
"""

from __future__ import annotations

import random
from argparse import Namespace
from collections import Counter

import pytest

from ml.datasets.make_episodes import (
    ALL_SHAPES,
    _build_shape_schedule,
    _episodes_per_virtual_day,
)


def test_build_shape_schedule_covers_every_shape_every_chunk() -> None:
    """One full chunk (= episodes_per_day) must contain every shape at least
    once -- that is what makes it round robin rather than plain shuffling."""
    rng = random.Random(0)
    shapes = ["a", "b", "c"]
    schedule = _build_shape_schedule(rng, shapes, n_episodes=9, episodes_per_day=3)
    for chunk_start in range(0, 9, 3):
        chunk = schedule[chunk_start : chunk_start + 3]
        assert set(chunk) == set(shapes)


def test_build_shape_schedule_is_reproducible_for_a_fixed_seed() -> None:
    shapes = list(ALL_SHAPES)
    a = _build_shape_schedule(random.Random(42), shapes, n_episodes=50, episodes_per_day=7)
    b = _build_shape_schedule(random.Random(42), shapes, n_episodes=50, episodes_per_day=7)
    assert a == b


def test_build_shape_schedule_handles_a_final_partial_chunk() -> None:
    rng = random.Random(1)
    schedule = _build_shape_schedule(rng, ["a", "b", "c"], n_episodes=8, episodes_per_day=3)
    assert len(schedule) == 8
    # Every shape still appears, even though 8 does not divide evenly by 3.
    assert set(schedule) == {"a", "b", "c"}


def test_build_shape_schedule_is_not_just_rng_choice() -> None:
    """Over many virtual days, counts per shape must be near-equal -- within
    one occurrence of each other, since every chunk round-robins through the
    full shape list exactly once (chunk_size == len(shapes) here)."""
    rng = random.Random(3)
    shapes = ["a", "b", "c", "d"]
    schedule = _build_shape_schedule(rng, shapes, n_episodes=400, episodes_per_day=4)
    counts = Counter(schedule)
    assert set(counts) == set(shapes)
    assert max(counts.values()) - min(counts.values()) <= 1


def _args(**overrides: object) -> Namespace:
    defaults = dict(
        shapes=list(ALL_SHAPES),
        normal_minutes=65.0,
        recover_minutes=10.0,
        fault_seconds_min=180,
        fault_seconds_max=600,
        ramp_minutes=10.0,
        small_step_seconds=300,
        intermittent_minutes=10.0,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def test_episodes_per_virtual_day_is_a_positive_int() -> None:
    n = _episodes_per_virtual_day(_args())
    assert isinstance(n, int)
    assert n >= 1


def test_episodes_per_virtual_day_shrinks_as_episodes_get_longer() -> None:
    short = _episodes_per_virtual_day(_args(normal_minutes=5.0, recover_minutes=1.0))
    long_ = _episodes_per_virtual_day(_args(normal_minutes=65.0, recover_minutes=10.0))
    assert short > long_


@pytest.mark.parametrize("shapes", [["cpu_hog"], list(ALL_SHAPES)])
def test_episodes_per_virtual_day_handles_any_shape_subset(shapes: list[str]) -> None:
    assert _episodes_per_virtual_day(_args(shapes=shapes)) >= 1
