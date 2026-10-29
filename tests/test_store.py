from datetime import date, datetime

import pytest

from stepper_quests.store import Store


def ts(*args):
    return datetime(*args).timestamp()


@pytest.fixture
def store(home_dir):
    s = Store(Store.default_path())
    yield s
    s.close()


def add(store, start, steps, end=None, max_spm=60, mean_spm=50.0, active=600.0):
    return store.upsert_session(None, start, end, steps, max_spm, mean_spm, active)


def test_default_path_honours_env(home_dir):
    assert Store.default_path() == home_dir / "steps.db"


def test_default_path_falls_back_to_home(tmp_path, monkeypatch):
    monkeypatch.delenv("STEPPER_QUESTS_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    path = Store.default_path()
    assert path == tmp_path / ".local/share/stepper-quests/steps.db"
    assert path.parent.is_dir()


def test_wal_mode(store):
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_upsert_inserts_then_updates(store):
    sid = add(store, ts(2026, 10, 29, 9), 100)
    assert store.upsert_session(sid, ts(2026, 10, 29, 9), ts(2026, 10, 29, 10), 250, 70, 55.0, 900.0) == sid
    rows = store.sessions_on_day(date(2026, 10, 29))
    assert len(rows) == 1
    assert rows[0]["steps"] == 250
    assert rows[0]["end"] == ts(2026, 10, 29, 10)
    assert rows[0]["max_spm"] == 70


def test_delete_session(store):
    sid = add(store, ts(2026, 10, 29, 9), 100)
    store.delete_session(sid)
    assert store.lifetime_steps() == 0


def test_lifetime_is_sum_of_sessions(store):
    add(store, ts(2026, 10, 27, 9), 100.5)
    add(store, ts(2026, 10, 28, 9), 200)
    add(store, ts(2026, 10, 29, 9), 300)
    assert store.lifetime_steps() == pytest.approx(600.5)


def test_lifetime_empty_is_zero(store):
    assert store.lifetime_steps() == 0


def test_steps_on_day(store):
    add(store, ts(2026, 10, 29, 9), 100)
    add(store, ts(2026, 10, 29, 18), 50)
    add(store, ts(2026, 10, 28, 9), 999)
    assert store.steps_on_day(date(2026, 10, 29)) == 150
    assert store.steps_on_day(date(2026, 10, 30)) == 0


def test_session_over_midnight_counts_for_start_day(store):
    add(store, ts(2026, 10, 28, 23, 50), 400, end=ts(2026, 10, 29, 0, 20))
    assert store.steps_on_day(date(2026, 10, 28)) == 400
    assert store.steps_on_day(date(2026, 10, 29)) == 0
    assert len(store.sessions_on_day(date(2026, 10, 28))) == 1
    assert store.sessions_on_day(date(2026, 10, 29)) == []


def test_sessions_on_day_ordered_by_start(store):
    add(store, ts(2026, 10, 29, 18), 50)
    add(store, ts(2026, 10, 29, 9), 100)
    assert [r["steps"] for r in store.sessions_on_day(date(2026, 10, 29))] == [100, 50]


def test_best_day(store):
    assert store.best_day() is None
    add(store, ts(2026, 10, 27, 9), 300)
    add(store, ts(2026, 10, 28, 9), 200)
    add(store, ts(2026, 10, 28, 19), 200)
    assert store.best_day() == (date(2026, 10, 28), 400)


def test_longest_session_steps(store):
    assert store.longest_session_steps() == 0
    add(store, ts(2026, 10, 27, 9), 300)
    add(store, ts(2026, 10, 28, 9), 700)
    assert store.longest_session_steps() == 700


def test_streak_counts_consecutive_days(store):
    for day in (26, 27, 28, 29):
        add(store, ts(2026, 10, day, 9), 100)
    assert store.streak_days(date(2026, 10, 29)) == 4


def test_streak_broken_by_gap(store):
    add(store, ts(2026, 10, 25, 9), 100)
    add(store, ts(2026, 10, 27, 9), 100)
    add(store, ts(2026, 10, 28, 9), 100)
    add(store, ts(2026, 10, 29, 9), 100)
    assert store.streak_days(date(2026, 10, 29)) == 3


def test_streak_starts_from_yesterday_before_first_session(store):
    add(store, ts(2026, 10, 27, 9), 100)
    add(store, ts(2026, 10, 28, 9), 100)
    assert store.streak_days(date(2026, 10, 29)) == 2


def test_streak_zero_when_today_and_yesterday_empty(store):
    add(store, ts(2026, 10, 26, 9), 100)
    assert store.streak_days(date(2026, 10, 29)) == 0


def test_streak_uses_start_day_attribution(store):
    add(store, ts(2026, 10, 27, 23, 50), 100, end=ts(2026, 10, 28, 0, 30))
    add(store, ts(2026, 10, 29, 9), 100)
    assert store.streak_days(date(2026, 10, 29)) == 1


def test_recent_daily_steps(store):
    add(store, ts(2026, 10, 25, 9), 999)
    add(store, ts(2026, 10, 27, 9), 100)
    add(store, ts(2026, 10, 29, 9), 50)
    add(store, ts(2026, 10, 29, 20), 25)
    assert store.recent_daily_steps(3, date(2026, 10, 29)) == [100, 0, 75]


def test_settings_roundtrip(store):
    assert store.get_setting("missing") is None
    assert store.get_setting("missing", 7) == 7
    store.set_setting("quest", {"id": "fellowship", "n": [1, 2]})
    assert store.get_setting("quest") == {"id": "fellowship", "n": [1, 2]}
    store.set_setting("quest", "mordor")
    assert store.get_setting("quest") == "mordor"


def test_settings_persist_across_instances(home_dir):
    path = Store.default_path()
    s = Store(path)
    s.set_setting("muted", True)
    s.close()
    s = Store(path)
    assert s.get_setting("muted") is True
    s.close()


def test_unlock_twice_returns_false(store):
    assert store.unlock("first-steps", ts(2026, 10, 29, 9), "hello") is True
    assert store.unlock("first-steps", ts(2026, 10, 29, 10)) is False
    assert store.unlocked() == [("first-steps", ts(2026, 10, 29, 9), "hello")]


def test_unlocked_ordered_by_time(store):
    store.unlock("b", ts(2026, 10, 29, 10))
    store.unlock("sting-glows:2026-10-29", ts(2026, 10, 29, 9))
    assert [name for name, _, _ in store.unlocked()] == ["sting-glows:2026-10-29", "b"]


def test_waypoints_idempotent(store):
    assert store.reached_waypoints("fellowship") == set()
    store.mark_waypoint("fellowship", "bree", ts(2026, 10, 29, 9))
    store.mark_waypoint("fellowship", "bree", ts(2026, 10, 29, 10))
    store.mark_waypoint("fellowship", "rivendell", ts(2026, 10, 29, 11))
    store.mark_waypoint("other", "x", ts(2026, 10, 29, 11))
    assert store.reached_waypoints("fellowship") == {"bree", "rivendell"}


def test_all_sessions_ordered_by_start(store):
    assert store.all_sessions() == []
    add(store, ts(2026, 10, 29, 9), 300)
    add(store, ts(2026, 10, 27, 9), 100)
    add(store, ts(2026, 10, 28, 9), 200)
    rows = store.all_sessions()
    assert [row["steps"] for row in rows] == [100, 200, 300]
    assert rows[0]["start"] == ts(2026, 10, 27, 9)


def test_repair_sessions_drops_crash_stubs_and_closes_open_rows(store):
    start = ts(2026, 10, 1, 9)
    add(store, start, 0.0, active=0.0)
    add(store, start + 100, 19.0, end=start + 160)
    add(store, start + 200, 500.0, active=300.0)
    add(store, start + 300, 30.0, active=0.0)
    add(store, start + 400, 800.0, end=start + 900, active=480.0)
    assert store.repair_sessions(20) == 4
    rows = [(r["start"], r["end"], r["steps"]) for r in store.all_sessions()]
    assert rows == [
        (start + 200, start + 500, 500.0),
        (start + 300, start + 300, 30.0),
        (start + 400, start + 900, 800.0),
    ]
    assert store.repair_sessions(20) == 0


def test_open_and_last_session(store):
    a = store.upsert_session(None, 1000.0, 1300.0, 200.0, 70, 65.0, 300.0)
    b = store.upsert_session(None, 2000.0, None, 50.0, 60, 60.0, 40.0)
    assert store.open_session()["id"] == b
    assert store.last_session()["id"] == a
    assert store.first_session_start() == 1000.0


def test_open_and_last_session_empty(store):
    assert store.open_session() is None
    assert store.last_session() is None
    assert store.first_session_start() is None


def test_waypoints_reached_between(store):
    store.mark_waypoint("q", "w1", 1100.0)
    store.mark_waypoint("q", "w2", 1200.0)
    store.mark_waypoint("q", "w3", 5000.0)
    store.mark_waypoint("other", "w9", 1150.0)
    assert store.waypoints_reached_between("q", 1000.0, 1300.0) == ["w1", "w2"]


def test_sessions_between(store):
    store.upsert_session(None, 1000.0, 1300.0, 200.0, 70, 65.0, 300.0)
    store.upsert_session(None, 2000.0, 2300.0, 100.0, 70, 65.0, 300.0)
    assert [r["start"] for r in store.sessions_between(1500.0, 2500.0)] == [2000.0]
