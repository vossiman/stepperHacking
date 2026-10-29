from datetime import date, datetime
from pathlib import Path

import pytest

from stepper_quests import journey_model as jm
from stepper_quests.progress import ACHIEVEMENTS
from stepper_quests.quests import load_quest, miles_to_steps
from stepper_quests.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"
TODAY = date(2026, 10, 29)


def ts(*args):
    return datetime(*args).timestamp()


@pytest.fixture
def quest():
    return load_quest(FIXTURE)


@pytest.fixture
def store(home_dir):
    s = Store(Store.default_path())
    yield s
    s.close()


def add(store, start, steps, mean_spm=50.0, active=600.0):
    return store.upsert_session(None, start, start + active, steps, 60, mean_spm, active)


def chapters(quest):
    return quest.volumes[0].parts[0].chapters


# pace


def test_pace_falls_back_without_recent_steps(store):
    assert jm.pace_steps_per_day(store, TODAY) == jm.DEFAULT_PACE == 1740


def test_pace_is_mean_over_active_days_only(store):
    add(store, ts(2026, 10, 29, 9), 1000)
    add(store, ts(2026, 10, 27, 9), 2000)
    add(store, ts(2026, 10, 27, 18), 1000)
    assert jm.pace_steps_per_day(store, TODAY) == pytest.approx(2000)


def test_pace_ignores_days_older_than_thirty(store):
    add(store, ts(2026, 9, 29, 9), 9000)
    add(store, ts(2026, 9, 30, 9), 3000)
    assert jm.pace_steps_per_day(store, TODAY) == pytest.approx(3000)


# chapter numbers


def test_chapter_miles_start_at_previous_waypoint(quest):
    a, b = chapters(quest)
    assert jm.chapter_miles(quest, a) == pytest.approx(20)
    assert jm.chapter_miles(quest, b) == pytest.approx(30)


def test_chapter_estimate(quest):
    b = chapters(quest)[1]
    est = jm.chapter_estimate(quest, b, metres_per_step=0.8, pace=2000)
    assert est.miles == pytest.approx(30)
    assert est.steps == pytest.approx(miles_to_steps(30, 0.8))
    assert est.days == pytest.approx(miles_to_steps(30, 0.8) / 2000)


def test_chapter_label(quest):
    est = jm.ChapterEstimate(miles=30.04, steps=60350.4, days=30.2)
    assert jm.chapter_label(est) == "30 mi, 60,350 steps, ~30 days"


def test_chapter_label_rounds_short_chapters_up_to_a_day():
    est = jm.ChapterEstimate(miles=0.4, steps=900, days=0.3)
    assert jm.chapter_label(est) == "0.4 mi, 900 steps, ~1 day"


# classification


def test_states_at_start(quest):
    position = quest.position(0)
    a, b = chapters(quest)
    assert jm.chapter_state(a, position) == "active"
    assert jm.chapter_state(b, position) == "ahead"
    assert [jm.waypoint_state(w, position) for w in a.waypoints] == ["done", "active", "ahead"]


def test_states_mid_quest(quest):
    position = quest.position(25)
    a, b = chapters(quest)
    assert jm.chapter_state(a, position) == "done"
    assert jm.chapter_state(b, position) == "active"
    assert [jm.waypoint_state(w, position) for w in b.waypoints] == ["active", "ahead"]


def test_waypoint_exactly_reached_is_done(quest):
    position = quest.position(20)
    a, b = chapters(quest)
    assert jm.chapter_state(a, position) == "done"
    assert jm.waypoint_state(a.waypoints[-1], position) == "done"
    assert jm.waypoint_state(b.waypoints[0], position) == "active"


def test_states_at_the_end(quest):
    position = quest.position(999)
    assert [jm.chapter_state(c, position) for c in chapters(quest)] == ["done", "done"]
    assert jm.waypoint_state(quest.waypoints[-1], position) == "done"


# road miles


def test_road_miles_interpolates_within_the_stretch(quest):
    # walkable 25 is halfway along the boat stretch from road mile 20 to 60
    assert jm.road_miles_walked(quest.position(25)) == pytest.approx(40)


def test_road_miles_at_the_end(quest):
    assert jm.road_miles_walked(quest.position(999)) == pytest.approx(80)


# today


def test_today_stats(store):
    add(store, ts(2026, 10, 29, 9), 1200, active=600)
    add(store, ts(2026, 10, 29, 15), 600, active=600)
    add(store, ts(2026, 10, 28, 9), 5000)
    stats = jm.today_stats(store, TODAY)
    assert stats == jm.DayStats(steps=1800, sessions=2, minutes=20, mean_spm=90)


def test_today_stats_empty(store):
    assert jm.today_stats(store, TODAY) == jm.DayStats(steps=0, sessions=0, minutes=0, mean_spm=0)


# achievements


def test_achievement_lookup_plain_and_repeatable():
    unlocked = [
        ("elevenses", 100.0, ""),
        ("sting-glows:2026-10-01", 200.0, "3000"),
        ("sting-glows:2026-10-20", 300.0, "4000"),
        ("road-goes-on:Part 1", 250.0, "Part 1"),
    ]
    lookup = jm.achievement_status(ACHIEVEMENTS, unlocked)
    assert lookup["elevenses"] == (100.0, "")
    assert lookup["sting-glows"] == (300.0, "4000")
    assert lookup["road-goes-on"] == (250.0, "Part 1")
    assert lookup["wander"] is None
    assert lookup["second-breakfast"] is None
    assert set(lookup) == {a.name for a in ACHIEVEMENTS}


def test_achievement_lookup_needs_exact_name_for_plain_ones():
    lookup = jm.achievement_status(ACHIEVEMENTS, [("elevenses:x", 1.0, "")])
    assert lookup["elevenses"] is None


# durations and projection


def test_duration_text():
    assert jm.duration_text(0.2) == "1 day"
    assert jm.duration_text(14.4) == "14 days"
    assert jm.duration_text(59.4) == "59 days"
    assert jm.duration_text(90) == "3 months"
    assert jm.duration_text(729) == "24 months"
    assert jm.duration_text(365.25 * 4) == "4 years"
    assert jm.duration_text(365.25 * 4 + 61) == "4 years 2 months"


def test_projection_line_without_pace(quest):
    pos = quest.position(0.0)
    line = jm.projection_line(quest, pos, 0.7, None)
    assert line == "80 road miles to the Crack of Doom. Your first walk sets the pace."


def test_projection_line_with_pace(quest):
    # walkable 25 is road mile 40; 25 walkable miles are left
    pos = quest.position(25)
    pace = miles_to_steps(25, 0.7) / 90
    line = jm.projection_line(quest, pos, 0.7, pace)
    assert line == "40 road miles to the Crack of Doom. About 3 months at your pace."


def test_projection_line_at_the_end(quest):
    assert jm.projection_line(quest, quest.position(999), 0.7, 2000) == (
        "You stand at the Crack of Doom."
    )


# latest walk


def test_latest_walk_none_without_sessions(store, quest):
    assert jm.latest_walk(store, quest) is None


def test_latest_walk_prefers_open_session(store, quest):
    store.upsert_session(None, 1000.0, 1300.0, 200.0, 70, 65.0, 300.0)
    store.upsert_session(None, 2000.0, None, 50.0, 60, 60.0, 40.0)
    w = jm.latest_walk(store, quest)
    assert w.live and w.steps == 50.0


def test_latest_walk_names_reached_waypoints(store, quest):
    store.upsert_session(None, 1000.0, 1300.0, 200.0, 70, 65.0, 300.0)
    store.mark_waypoint(quest.id, quest.waypoints[0].id, 1100.0)
    assert jm.latest_walk(store, quest).reached == [quest.waypoints[0].name]


def test_latest_walk_summary_fields(store, quest):
    store.upsert_session(None, 1000.0, 1300.0, 200.0, 74, 66.0, 300.0)
    store.mark_waypoint(quest.id, "hobbiton", 900.0)
    store.mark_waypoint(quest.id, "bucklebury", 1400.0)
    assert jm.latest_walk(store, quest) == jm.WalkSummary(
        live=False, start=1000.0, steps=200.0, minutes=5.0, mean_spm=66.0, max_spm=74,
        reached=[],
    )


def test_latest_walk_open_session_sees_later_waypoints(store, quest):
    store.upsert_session(None, 1000.0, None, 200.0, 74, 66.0, 300.0)
    store.mark_waypoint(quest.id, "hobbiton", 5000.0)
    assert jm.latest_walk(store, quest).reached == ["Hobbiton"]


# start pill


def test_start_pill():
    today = date(2026, 10, 29)
    assert jm.start_pill(ts(2026, 10, 29, 14, 33), today) == "today 14:33"
    assert jm.start_pill(ts(2026, 10, 28, 9, 10), today) == "yesterday 09:10"
    assert jm.start_pill(ts(2026, 10, 27, 9, 10), today) == "Tue 27 Oct"
    assert jm.start_pill(ts(2026, 10, 5, 9, 10), today) == "Mon 5 Oct"


# week


def test_week_stats_boundaries(store):
    # today is Wednesday 2026-10-28; Sunday 23:50 counts last week, Monday 00:10 this week
    today = date(2026, 10, 28)
    add(store, ts(2026, 10, 25, 23, 50), 300)
    add(store, ts(2026, 10, 26, 0, 10), 500)
    add(store, ts(2026, 10, 28, 9), 200)
    add(store, ts(2026, 10, 19, 0, 0), 1000)  # last Monday's start, outside last7
    add(store, ts(2026, 10, 18, 23, 59), 4000)  # the week before last
    w = jm.week_stats(store, today)
    assert w.this_week == 700
    assert w.last_week == 1300
    assert w.last7 == [0, 0, 0, 300, 500, 0, 200]
    assert w.labels == ["T", "F", "S", "S", "M", "T", "W"]
    assert w.best_day == (date(2026, 10, 26), 500)


def test_week_stats_empty(store):
    w = jm.week_stats(store, date(2026, 10, 28))
    assert w.last7 == [0] * 7
    assert w.this_week == 0 and w.last_week == 0
    assert w.best_day is None


def test_week_line():
    w = jm.WeekStats(
        last7=[0, 1520, 0, 0, 0, 0, 620], labels=list("FSSMTWT"),
        this_week=2140, last_week=3800, best_day=(date(2026, 10, 24), 1520),
    )
    assert jm.week_line(w) == "This week 2,140 steps · last week 3,800 · best day 1,520 (Sat)"


def test_week_line_without_best_day():
    w = jm.WeekStats(last7=[0] * 7, labels=list("FSSMTWT"), this_week=0,
                     last_week=3800, best_day=None)
    assert jm.week_line(w) == "This week 0 steps · last week 3,800"


# records


def test_records_empty(store, quest):
    r = jm.records(store, quest, quest.position(0.0), 0.7, date(2026, 10, 28))
    records, totals, pace = dict(r.records), dict(r.totals), dict(r.pace)
    assert [label for label, _ in r.records] == [
        "Best day", "Longest walk", "Fastest walk", "Peak cadence", "Longest streak",
        "Best week", "Earliest start",
    ]
    assert set(records.values()) == {"none yet"}
    assert totals == {
        "Steps": "0",
        "Distance": "0 km, 0 road miles",
        "Walks": "0",
        "Time walking": "0 min",
        "Walking days": "0",
        "Waypoints reached": "1 of 5",
        "Chapters done": "0 of 2",
    }
    # the mini quest has no Rivendell, so that row is left out
    assert [label for label, _ in r.pace] == [
        "Per walking day", "Per week 4-wk avg", "Next waypoint", "End of chapter",
        "Mount Doom", "Frodo's pace",
    ]
    assert pace["Per walking day"] == "none yet"
    assert pace["Per week 4-wk avg"] == "none yet"
    assert pace["Next waypoint"] == f"{miles_to_steps(10, 0.7):,.0f} steps"
    assert pace["End of chapter"] == "none yet"
    assert pace["Mount Doom"] == "none yet"
    assert pace["Frodo's pace"] == "you are at 0.0% of his 6 months"


def test_records_with_sessions(store, quest):
    today = date(2026, 10, 28)
    add(store, ts(2026, 10, 20, 7, 5), 1000, mean_spm=60, active=600)
    add(store, ts(2026, 10, 21, 18), 3000, mean_spm=70, active=1800)
    add(store, ts(2026, 10, 27, 9), 500, mean_spm=50, active=300)
    add(store, ts(2026, 10, 28, 9), 1500, mean_spm=55, active=900)
    store.upsert_session(None, ts(2026, 10, 28, 12), ts(2026, 10, 28, 12, 5), 400, 90, 80, 300)
    position = quest.position(25)
    r = jm.records(store, quest, position, 0.7, today)
    records, totals, pace = dict(r.records), dict(r.totals), dict(r.pace)
    assert records == {
        "Best day": "3,000 steps · Wed 21 Oct",
        "Longest walk": "3,000 steps · 30 min",
        "Fastest walk": "80 spm mean",
        "Peak cadence": "90 spm",
        "Longest streak": "2 days",
        "Best week": "4,000 steps · week of Mon 19 Oct",
        "Earliest start": "07:05",
    }
    assert totals["Steps"] == "6,400"
    assert totals["Distance"] == "4.48 km, 40.0 road miles"
    assert totals["Walks"] == "5"
    assert totals["Time walking"] == "1 h 05 min"
    assert totals["Walking days"] == "4 of 9 since start"
    assert totals["Waypoints reached"] == "3 of 5"
    assert totals["Chapters done"] == "1 of 2"
    pace_per_day = jm.pace_steps_per_day(store, today)
    assert pace_per_day == 1600
    assert pace["Per walking day"] == "1,600 steps"
    assert pace["Per week 4-wk avg"] == "1,600 steps"
    # 5 miles to Far Bank at walkable 30; mean walk is 1,280 steps
    to_next = miles_to_steps(5, 0.7)
    walks = -(-to_next // 1280)
    assert pace["Next waypoint"] == f"{to_next:,.0f} steps, about {walks:.0f} walks"
    assert pace["End of chapter"] == jm.duration_text(miles_to_steps(25, 0.7) / 1600)
    assert pace["Mount Doom"] == jm.duration_text(miles_to_steps(25, 0.7) / 1600)
    assert pace["Frodo's pace"] == "you are at 50.0% of his 6 months"


def test_records_targets_reached_at_the_end(store, quest):
    add(store, ts(2026, 10, 28, 9), 1500)
    r = jm.records(store, quest, quest.position(999), 0.7, date(2026, 10, 28))
    pace = dict(r.pace)
    assert pace["Next waypoint"] == "reached"
    assert pace["End of chapter"] == "reached"
    assert pace["Mount Doom"] == "reached"
    assert pace["Frodo's pace"] == "you are at 100.0% of his 6 months"


def test_records_rivendell_row(store, quest):
    quest.waypoints[3].name = "Rivendell, the Last Homely House"
    add(store, ts(2026, 10, 28, 9), 1500)
    pace = dict(jm.records(store, quest, quest.position(5), 0.7, date(2026, 10, 28)).pace)
    assert pace["Rivendell"] == jm.duration_text(miles_to_steps(25, 0.7) / 1500)
    pace = dict(jm.records(store, quest, quest.position(30), 0.7, date(2026, 10, 28)).pace)
    assert pace["Rivendell"] == "reached"


# history


def test_history_days_empty(store, quest):
    assert jm.history_days(store, quest, date(2026, 10, 28)) == []


def test_history_days_starts_at_first_session(store, quest):
    today = date(2026, 10, 28)
    add(store, ts(2026, 10, 25, 9), 1200, mean_spm=60, active=600)
    add(store, ts(2026, 10, 28, 9), 300, active=300)
    add(store, ts(2026, 10, 28, 15), 300, active=300)
    store.mark_waypoint(quest.id, "hobbiton", ts(2026, 10, 25, 9, 5))
    rows = jm.history_days(store, quest, today)
    assert [r.day for r in rows] == [date(2026, 10, d) for d in (28, 27, 26, 25)]
    assert rows[0] == jm.DayRow(date(2026, 10, 28), 600, 2, 10, 60, [])
    assert rows[1] == jm.DayRow(date(2026, 10, 27), 0, 0, 0, 0, [])
    assert rows[3] == jm.DayRow(date(2026, 10, 25), 1200, 1, 10, 120, ["Hobbiton"])


def test_history_days_caps_at_window(store, quest):
    add(store, ts(2026, 8, 1, 9), 100)
    rows = jm.history_days(store, quest, date(2026, 10, 28))
    assert len(rows) == 30
    assert rows[-1].day == date(2026, 9, 29)


def test_walking_days_text():
    rows = [jm.DayRow(date(2026, 10, d), s, 1 if s else 0, 0, 0, [])
            for d, s in ((28, 600), (27, 0), (26, 10))]
    assert jm.walking_days_text(rows) == "Last 30 days. Walking days 2 of 3."
