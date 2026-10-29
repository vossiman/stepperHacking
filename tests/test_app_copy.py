from pathlib import Path

import pytest

from stepper_quests.copy import end_message, format_steps, start_message, tooltip
from stepper_quests.counter import Session
from stepper_quests.quests import load_quest

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"
MPS = 0.7


@pytest.fixture
def quest():
    return load_quest(FIXTURE)


def test_format_steps_uses_comma_thousands_and_rounds():
    assert format_steps(0) == "0"
    assert format_steps(1812.4) == "1,812"
    assert format_steps(1234567.6) == "1,234,568"


def test_start_message_names_both_waypoints(quest):
    # Hobbiton is 10 walkable miles out: 16093.44 m / 0.7 m per step.
    assert start_message(quest.position(0.0), MPS) == "Leaving Bag End. 22,991 steps to Hobbiton."


def test_start_message_counts_from_current_position(quest):
    assert start_message(quest.position(5.0), MPS) == "Leaving Bag End. 11,495 steps to Hobbiton."


def test_start_message_at_end_of_road(quest):
    assert start_message(quest.position(1000.0), MPS) == "Leaving Bree. The road ends here."


def test_end_message(quest):
    session = Session(start=1000.0, end=1000.0 + 31 * 60, steps=1812.4)
    assert (
        end_message(session, quest.position(5.0), MPS)
        == "1,812 steps in 31 min. Hobbiton is 11,495 steps away."
    )


def test_end_message_short_session_says_one_minute(quest):
    session = Session(start=1000.0, end=1020.0, steps=20.0)
    assert end_message(session, quest.position(0.0), MPS).startswith("20 steps in 1 min.")


def test_end_message_at_end_of_road(quest):
    session = Session(start=1000.0, end=1600.0, steps=700.0)
    assert (
        end_message(session, quest.position(1000.0), MPS)
        == "700 steps in 10 min. The road ends at Bree."
    )


def test_tooltip_variants():
    assert tooltip("stepping", 62, 1812.0) == "stepping, 62 spm, 1,812 today"
    assert tooltip("idle", 0, 0.0) == "idle, 0 today"
    assert tooltip("reconnecting", 0, 500.0) == "reconnecting"
