import json
from datetime import datetime
from pathlib import Path

import pytest

from stepper_quests.counter import Session
from stepper_quests.progress import ACHIEVEMENTS, Notice, Progress, Settings
from stepper_quests.journey_model import achievement_status
from stepper_quests.quests import Quest, load_quest, miles_to_steps
from stepper_quests.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"


@pytest.fixture
def store(home_dir):
    s = Store(Store.default_path())
    yield s
    s.close()


@pytest.fixture
def quest():
    return load_quest(FIXTURE)


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def progress(store, quest, settings):
    return Progress(store, quest, settings)


def ts(y, mo, d, h=12, mi=0):
    return datetime(y, mo, d, h, mi).timestamp()


def add_session(store, start, steps, duration=600.0):
    store.upsert_session(None, start, start + duration, steps, 100, 90.0, duration)
    return Session(start=start, end=start + duration, steps=steps)


def steps_for(miles):
    return miles_to_steps(miles, 0.7) + 1


def names(store):
    return {row[0] for row in store.unlocked()}


def test_waypoint_notice_once(progress, store):
    notices = progress.on_session_progress(steps_for(10))
    assert notices == [Notice("waypoint", "Hobbiton", "Down the hill.")]
    assert store.reached_waypoints("mini") == {"bag-end", "hobbiton"}
    assert progress.on_session_progress(steps_for(10)) == []


def test_waypoint_counts_store_plus_extra(progress, store):
    add_session(store, ts(2026, 10, 1), steps_for(10))
    notices = progress.on_session_progress(miles_to_steps(10, 0.7))
    assert [n.title for n in notices] == ["Hobbiton", "Bucklebury"]


def test_sync_silently_marks_without_notices(progress, store):
    add_session(store, ts(2026, 10, 1), steps_for(30))
    progress.sync_silently()
    assert store.reached_waypoints("mini") == {"bag-end", "hobbiton", "bucklebury", "far-bank"}
    assert progress.on_session_progress(0) == []


def test_metres_per_step_change_does_not_refire(progress, store, settings):
    add_session(store, ts(2026, 10, 1), 46000)
    assert [n.title for n in progress.on_session_progress(0)] == ["Hobbiton", "Bucklebury"]
    settings.metres_per_step = 1.0
    assert progress.on_session_progress(0) == []


def test_second_breakfast_needs_two_hours(progress, store):
    add_session(store, ts(2026, 10, 1, 13), 100)
    late = add_session(store, ts(2026, 10, 1, 14, 59), 50)
    assert "second-breakfast" not in names(store)
    titles = [n.title for n in progress.on_session_ended(late)]
    assert "Second Breakfast" not in titles
    later = add_session(store, ts(2026, 10, 1, 15), 50)
    notices = progress.on_session_ended(later)
    assert Notice("achievement", "Second Breakfast", ACHIEVEMENTS[0].body) in notices
    assert "second-breakfast" in names(store)


def test_elevenses(progress, store):
    afternoon = add_session(store, ts(2026, 10, 1, 11), 100)
    assert "Elevenses" not in [n.title for n in progress.on_session_ended(afternoon)]
    morning = add_session(store, ts(2026, 10, 2, 10, 59), 50)
    assert "Elevenses" in [n.title for n in progress.on_session_ended(morning)]


def test_streak_seven(progress, store):
    for day in range(1, 7):
        last = add_session(store, ts(2026, 10, day), 100)
    titles = [n.title for n in progress.on_session_ended(last)]
    assert "Hobbit's Pace" not in titles
    seventh = add_session(store, ts(2026, 10, 7), 100)
    titles = [n.title for n in progress.on_session_ended(seventh)]
    assert "Hobbit's Pace" in titles
    assert "Rangers of the North" not in titles


def test_streak_counts_unpersisted_session(progress, store):
    for day in range(1, 7):
        add_session(store, ts(2026, 10, day), 100)
    seventh = Session(start=ts(2026, 10, 7), end=ts(2026, 10, 7, 13), steps=100)
    assert "Hobbit's Pace" in [n.title for n in progress.on_session_ended(seventh)]


def test_long_expected_party(progress, store):
    first = add_session(store, ts(2026, 10, 1), 99999)
    assert "Long-expected Party" not in [n.title for n in progress.on_session_ended(first)]
    second = add_session(store, ts(2026, 10, 2), 1)
    assert "Long-expected Party" in [n.title for n in progress.on_session_ended(second)]


def test_best_day_repeatable_with_note(progress, store):
    first = add_session(store, ts(2026, 10, 1), 1000)
    assert "Sting Glows" not in [n.title for n in progress.on_session_ended(first)]
    tie = add_session(store, ts(2026, 10, 2), 1000)
    assert "Sting Glows" not in [n.title for n in progress.on_session_ended(tie)]
    more = add_session(store, ts(2026, 10, 2, 14), 500)
    assert "Sting Glows" in [n.title for n in progress.on_session_ended(more)]
    unlocked = {row[0]: row[2] for row in store.unlocked()}
    assert "sting-glows:2026-10-01" not in unlocked
    assert unlocked["sting-glows:2026-10-02"] == "1500"


def test_longest_session_repeatable_with_note(progress, store):
    first = add_session(store, ts(2026, 10, 1), 1000)
    assert "Not all those who wander" not in [n.title for n in progress.on_session_ended(first)]
    tie = add_session(store, ts(2026, 10, 2), 1000)
    assert "Not all those who wander" not in [n.title for n in progress.on_session_ended(tie)]
    more = add_session(store, ts(2026, 10, 3), 1200.4)
    assert "Not all those who wander" in [n.title for n in progress.on_session_ended(more)]
    unlocked = {row[0]: row[2] for row in store.unlocked()}
    assert unlocked["wander:1200"] == "1200"
    assert not any(name.startswith("wander:1000") for name in unlocked)


def test_part_completed_notice(progress, store):
    session = add_session(store, ts(2026, 10, 1), steps_for(50))
    progress.on_session_progress(0)
    notices = progress.on_session_ended(session)
    parts = [n for n in notices if n.kind == "part"]
    assert len(parts) == 1
    assert parts[0].title == "The Road Goes Ever On"
    assert "Volume One / Part One" in parts[0].body
    unlocked = {row[0]: row[2] for row in store.unlocked()}
    assert unlocked["road-goes-on:Volume One / Part One"] == "Volume One / Part One"
    later = add_session(store, ts(2026, 10, 2), 10)
    assert [n for n in progress.on_session_ended(later) if n.kind == "part"] == []


def test_frodo_parts_have_distinct_keys(store):
    frodo = load_quest(Quest.default_path())
    progress = Progress(store, frodo, Settings())
    for w in frodo.waypoints:
        store.mark_waypoint(frodo.id, w.id, 0.0)
    labels = progress._completed_parts(1.0)
    assert len(labels) == 4
    keys = [name for name, _, _ in store.unlocked() if name.startswith("road-goes-on:")]
    assert len(set(keys)) == 4
    assert "road-goes-on:The Two Towers / Part 2 (Frodo and Sam)" in keys
    assert "road-goes-on:The Return of the King / Part 2 (Frodo and Sam)" in keys
    status = achievement_status(ACHIEVEMENTS, store.unlocked())
    assert status["road-goes-on"] is not None


def test_part_completed_before_startup_is_silent(progress, store):
    add_session(store, ts(2026, 10, 1), steps_for(50))
    progress.sync_silently()
    later = add_session(store, ts(2026, 10, 2), 10)
    assert [n for n in progress.on_session_ended(later) if n.kind == "part"] == []


def test_achievement_table_is_complete():
    titles = {a.title for a in ACHIEVEMENTS}
    assert titles == {
        "Second Breakfast", "Elevenses", "Hobbit's Pace", "Rangers of the North",
        "Long-expected Party", "Sting Glows", "Not all those who wander",
        "The Road Goes Ever On",
    }
    assert all(a.condition and a.body for a in ACHIEVEMENTS)
    assert not any("\u2014" in a.body + a.condition for a in ACHIEVEMENTS)


def test_notices_round_trip_through_json():
    from stepper_quests.progress import notices_from_json, notices_to_json

    notices = [Notice("achievement", "Elevenses", "Out early."), Notice("part", "Road", "Done.")]
    data = notices_to_json(notices)
    assert data[0] == {"title": "Elevenses", "body": "Out early.", "kind": "achievement"}
    assert json.loads(json.dumps(data)) == data
    assert notices_from_json(data) == notices
    assert notices_from_json(None) == []
