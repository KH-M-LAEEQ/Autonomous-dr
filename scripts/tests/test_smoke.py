"""Tests for scripts/smoke.py's check 4 helper: structure, not values.

`scripts/` is a standalone-scripts directory, not an installed package (see
`[tool.setuptools] packages` in pyproject.toml), so this file imports
`smoke` the same way `smoke.py` itself reaches `core/` -- by putting the
module's own directory on `sys.path` before importing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import smoke

from core.providers.simulated import applicable_signals
from core.signals import ALL_COLLECTED_SIGNALS

KIND = "web_service"
_APPLICABLE = set(applicable_signals(KIND))
_NOT_APPLICABLE = set(ALL_COLLECTED_SIGNALS) - _APPLICABLE


def _full_valid_window(overrides: dict[str, float] | None = None) -> dict[str, list[float]]:
    """Every applicable signal present with a normal-looking value, every
    non-applicable signal absent -- the structurally correct case."""
    values = {signal: [1.0] for signal in _APPLICABLE}
    if overrides:
        for signal, value in overrides.items():
            values[signal] = [value]
    return values


def test_a_structurally_correct_window_has_no_problems() -> None:
    assert smoke.applicability_problems(KIND, _full_valid_window()) == []


def test_a_real_zero_on_an_applicable_signal_passes() -> None:
    """The headline case: error_rate_5xx == 0.0 is a real, common reading
    (nothing went wrong), not evidence of a null-vs-zero bug."""
    window = _full_valid_window({"error_rate_5xx": 0.0})
    assert smoke.applicability_problems(KIND, window) == []


def test_every_applicable_signal_zero_still_passes() -> None:
    """Values are not inspected at all for applicable signals -- even
    every single one reading exactly 0.0 is structurally fine."""
    window = {signal: [0.0] for signal in _APPLICABLE}
    assert smoke.applicability_problems(KIND, window) == []


def test_a_zero_filled_non_applicable_signal_fails() -> None:
    """The regression this check exists for: a signal the applicability
    map says this kind does NOT report showing up anyway -- even at 0.0,
    even ESPECIALLY at 0.0, since that is exactly what null-as-zero
    writing looks like."""
    assert _NOT_APPLICABLE, "fixture assumption: web_service has some inapplicable signals"
    bogus_signal = sorted(_NOT_APPLICABLE)[0]
    window = _full_valid_window({bogus_signal: 0.0})

    problems = smoke.applicability_problems(KIND, window)

    assert len(problems) == 1
    assert bogus_signal in problems[0]
    assert "NOT applicable" in problems[0]


def test_a_non_applicable_signal_with_a_real_value_still_fails() -> None:
    """Not just a zero-filled artifact -- ANY value on a non-applicable
    signal is wrong, because that signal should never have been written
    for this resource kind at all."""
    bogus_signal = sorted(_NOT_APPLICABLE)[0]
    window = _full_valid_window({bogus_signal: 42.0})

    problems = smoke.applicability_problems(KIND, window)

    assert len(problems) == 1
    assert bogus_signal in problems[0]


def test_a_missing_applicable_signal_fails() -> None:
    window = _full_valid_window()
    missing_signal = sorted(_APPLICABLE)[0]
    del window[missing_signal]

    problems = smoke.applicability_problems(KIND, window)

    assert len(problems) == 1
    assert missing_signal in problems[0]
    assert "missing/null" in problems[0]


def test_an_empty_list_for_an_applicable_signal_counts_as_missing() -> None:
    """InfluxDB has no null -- an absent field reads back as a missing
    key, not an empty list, but guard the empty-list case too since
    `window.values.get(signal)` is the exact shape `core.influx.
    query_recent_window` returns."""
    window = _full_valid_window()
    signal = sorted(_APPLICABLE)[0]
    window[signal] = []

    problems = smoke.applicability_problems(KIND, window)

    assert any(signal in p and "missing/null" in p for p in problems)


def test_every_kind_is_internally_consistent_with_the_applicability_map() -> None:
    """Sanity check on the fixtures above, not the function under test: a
    structurally correct window for every resource kind in the schema must
    report zero problems."""
    for kind in ("web_service", "database", "cache", "worker", "load_balancer"):
        applicable = set(applicable_signals(kind))
        window = {signal: [1.0] for signal in applicable}
        assert smoke.applicability_problems(kind, window) == []
