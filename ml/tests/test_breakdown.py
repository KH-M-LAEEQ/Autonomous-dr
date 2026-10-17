"""Tests for ml/harness/breakdown.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ml.harness.breakdown import (
    _Row,
    analyze_episode_level,
    analyze_fault_types,
    render_markdown,
)
from ml.harness.evaluate import FaultInterval

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_cpu_hog_sudden_and_intermittent_are_separate_rows() -> None:
    """`cpu_hog` covers two shapes -- a sudden spike (episode 0) and an
    intermittent burst (episode 1). Pooling them by fault type alone hides
    that the intermittent shape detects far worse; grouping by
    `(fault_type, shape)` must keep them as two distinct rows."""
    sudden = FaultInterval(
        episode=0,
        fault_type="cpu_hog",
        start=_T0,
        end=_T0 + timedelta(seconds=40),
        shape="cpu_hog",
    )
    intermittent = FaultInterval(
        episode=1,
        fault_type="cpu_hog",
        start=_T0 + timedelta(seconds=1000),
        end=_T0 + timedelta(seconds=1040),
        shape="intermittent",
    )
    episode_meta = {0: sudden, 1: intermittent}
    intervals_by_resource = {"r1": [sudden, intermittent]}

    rows = [
        _Row(
            resource_id="r1",
            episode=0,
            phase="other",
            timestamp=sudden.start,
            true_label=True,
            breach=True,
        ),
        _Row(
            resource_id="r1",
            episode=1,
            phase="other",
            timestamp=intermittent.start,
            true_label=True,
            breach=False,
        ),
    ]
    predictions = {"threshold": rows}

    fault_type_stats, _seen_ids, _detected_ids = analyze_fault_types(
        predictions, intervals_by_resource, episode_meta, grace=timedelta(0)
    )

    assert set(fault_type_stats) == {("cpu_hog", "cpu_hog"), ("cpu_hog", "intermittent")}
    assert fault_type_stats[("cpu_hog", "cpu_hog")]["threshold"].episodes == 1
    assert fault_type_stats[("cpu_hog", "cpu_hog")]["threshold"].detected == 1
    assert fault_type_stats[("cpu_hog", "intermittent")]["threshold"].episodes == 1
    assert fault_type_stats[("cpu_hog", "intermittent")]["threshold"].detected == 0

    episode_level = analyze_episode_level(fault_type_stats, ("threshold",))
    markdown = render_markdown(
        dataset_version="vtest",
        fault_type_stats=fault_type_stats,
        missed_by_both={},
        phase_counts={},
        burst_rows=[],
        episode_level=episode_level,
        missed_window_stats={},
        sensitivity={},
        detectors=("threshold",),
    )

    cpu_hog_rows = [line for line in markdown.splitlines() if line.startswith("| `cpu_hog`")]
    assert len(cpu_hog_rows) == 2
    assert any("| `cpu_hog` |" in line and "`intermittent`" in line for line in cpu_hog_rows)
    assert any(
        "| `cpu_hog` |" in line and "| `cpu_hog` | `cpu_hog` |" in line for line in cpu_hog_rows
    )
