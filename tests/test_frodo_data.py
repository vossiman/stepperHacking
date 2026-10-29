import json

import pytest

from stepper_quests.quests import Quest, load_quest

PATH = Quest.default_path()


@pytest.fixture(scope="module")
def quest():
    return load_quest(PATH)


@pytest.fixture(scope="module")
def raw():
    return json.loads(PATH.read_text(encoding="utf-8"))


def by_id(quest, wid):
    return next(w for w in quest.waypoints if w.id == wid)


def test_loads(quest):
    assert quest.id == "frodo"
    assert quest.title == "Frodo's Road"
    structure = [(v.title, [p.title for p in v.parts]) for v in quest.volumes]
    assert structure == [
        ("The Fellowship of the Ring", ["Part 1", "Part 2"]),
        ("The Two Towers", ["Part 2 (Frodo and Sam)"]),
        ("The Return of the King", ["Part 2 (Frodo and Sam)"]),
    ]
    assert quest.waypoints[0].road_miles == 0
    assert 400 <= len(quest.waypoints) <= 650


def test_miles_monotonic(raw):
    miles = [
        w["road_miles"]
        for v in raw["volumes"]
        for p in v["parts"]
        for c in p["chapters"]
        for w in c["waypoints"]
    ]
    assert miles == sorted(miles)


@pytest.mark.parametrize(
    "wid, expected",
    [("rivendell", 458), ("caras-galadhon", 920), ("parth-galen", 1309)],
)
def test_stage_totals(quest, wid, expected):
    assert by_id(quest, wid).road_miles == pytest.approx(expected, rel=0.05)


def test_mount_doom_total(quest):
    last = quest.waypoints[-1]
    assert last.chapter.title == "Mount Doom"
    assert last.road_miles == pytest.approx(1779, rel=0.05)


def test_foot_gaps_at_most_four_miles(quest):
    pairs = zip(quest.waypoints, quest.waypoints[1:])
    gaps = [b.road_miles - a.road_miles for a, b in pairs if b.mode == "foot"]
    assert max(gaps) <= 6
    assert sum(1 for g in gaps if g > 4) <= 5


def test_every_waypoint_has_story(quest):
    for w in quest.waypoints:
        assert w.name.strip(), w.id
        assert w.story.strip(), w.id
        assert w.chapter.leg.strip(), w.chapter.title


@pytest.mark.parametrize("path", [PATH, PATH.with_name("SOURCES.md")], ids=lambda p: p.name)
def test_no_em_dashes(path):
    assert "\u2014" not in path.read_text(encoding="utf-8")


def test_modes_valid(quest):
    assert {w.mode for w in quest.waypoints} == {"foot", "horse", "boat", "carried"}
    chapters_by_mode = {}
    for w in quest.waypoints:
        chapters_by_mode.setdefault(w.mode, set()).add(w.chapter.title)
    assert chapters_by_mode["horse"] == {"Flight to the Ford"}
    assert chapters_by_mode["carried"] == {"Mount Doom"}
    assert chapters_by_mode["boat"] <= {
        "Farewell to Lorien",
        "The Great River",
        "The Breaking of the Fellowship",
    }


def test_ridden_and_boat_gaps_at_most_ten_walkable_miles(quest):
    pairs = zip(quest.waypoints, quest.waypoints[1:])
    gaps = {
        (a.id, b.id): (b.road_miles - a.road_miles) / quest.ratios[b.mode]
        for a, b in pairs
        if b.mode in ("boat", "horse")
    }
    assert gaps
    too_long = {k: v for k, v in gaps.items() if v > 10}
    assert too_long == {}
