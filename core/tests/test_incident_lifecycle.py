"""Tests for core/incidents.py's state machine. Pure validation -- no DB."""

from __future__ import annotations

import pytest

from core.incidents import VALID_TRANSITIONS, InvalidTransition, check_transition
from core.models.enums import IncidentState


def test_open_can_move_to_deciding() -> None:
    check_transition(IncidentState.OPEN, IncidentState.DECIDING)


def test_open_can_move_to_failed() -> None:
    check_transition(IncidentState.OPEN, IncidentState.FAILED)


def test_open_cannot_jump_straight_to_resolved() -> None:
    with pytest.raises(InvalidTransition):
        check_transition(IncidentState.OPEN, IncidentState.RESOLVED)


def test_deciding_can_move_to_acting() -> None:
    check_transition(IncidentState.DECIDING, IncidentState.ACTING)


def test_acting_can_resolve() -> None:
    check_transition(IncidentState.ACTING, IncidentState.RESOLVED)


@pytest.mark.parametrize("terminal", [IncidentState.RESOLVED, IncidentState.FAILED])
def test_terminal_states_have_no_outgoing_transitions(terminal: IncidentState) -> None:
    assert VALID_TRANSITIONS[terminal] == frozenset()
    with pytest.raises(InvalidTransition):
        check_transition(terminal, IncidentState.OPEN)


def test_every_state_has_a_row_in_the_table() -> None:
    assert set(VALID_TRANSITIONS) == set(IncidentState)
