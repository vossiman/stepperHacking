import json
from pathlib import Path

import pytest

from stepper_quests.quests import (
    Quest,
    load_quest,
    miles_to_steps,
    steps_to_miles,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"


@pytest.fixture
def quest():
    return load_quest(FIXTURE)


def write_variant(tmp_path, mutate):
    data = json.loads(FIXTURE.read_text())
    mutate(data)
    path = tmp_path / "quest.json"
    path.write_text(json.dumps(data))
    return path


def wp(data, index):
    chapters = data["volumes"][0]["parts"][0]["chapters"]
    flat = [w for c in chapters for w in c["waypoints"]]
    return flat[index]


def test_load_flattens_waypoints_with_back_references(quest):
    assert quest.id == "mini"
    assert quest.title == "Mini Quest"
    assert [w.id for w in quest.waypoints] == [
        "bag-end", "hobbiton", "bucklebury", "far-bank", "bree",
    ]
    bree = quest.waypoints[-1]
    assert bree.chapter.title == "Chapter B"
    assert bree.chapter.leg == "Down the river to Bree"
    assert bree.part.title == "Part One"
    assert bree.volume.title == "Volume One"
    assert bree in bree.chapter.waypoints


def test_walkable_miles_apply_ratio(quest):
    miles = [w.walkable_miles for w in quest.waypoints]
    assert miles == pytest.approx([0, 10, 20, 30, 50])
    far_bank = quest.waypoints[3]
    assert far_bank.walkable_miles - quest.waypoints[2].walkable_miles == pytest.approx(10)
    assert quest.total_walkable_miles == pytest.approx(50)


def test_position_mid_leg(quest):
    pos = quest.position(25)
    assert pos.reached.id == "bucklebury"
    assert pos.next.id == "far-bank"
    assert pos.fraction_to_next == pytest.approx(0.5)
    assert pos.miles_to_next == pytest.approx(5)
    assert pos.chapter.title == "Chapter B"
    assert pos.part.title == "Part One"
    assert pos.chapter_fraction == pytest.approx(5 / 30)
    assert pos.part_fraction == pytest.approx(25 / 50)


def test_position_exactly_on_waypoint(quest):
    pos = quest.position(10)
    assert pos.reached.id == "hobbiton"
    assert pos.next.id == "bucklebury"
    assert pos.fraction_to_next == 0.0


def test_position_at_start(quest):
    pos = quest.position(0)
    assert pos.reached.id == "bag-end"
    assert pos.chapter_fraction == 0.0
    assert pos.part_fraction == 0.0


def test_position_past_end_has_no_next(quest):
    pos = quest.position(1000)
    assert pos.reached.id == "bree"
    assert pos.next is None
    assert pos.chapter is pos.reached.chapter
    assert pos.part is pos.reached.part
    assert pos.fraction_to_next == 0.0
    assert pos.miles_to_next == 0.0
    assert pos.chapter_fraction == 1.0
    assert pos.part_fraction == 1.0


def test_steps_miles_roundtrip():
    assert steps_to_miles(1609.344 / 0.7) == pytest.approx(1.0)
    assert steps_to_miles(1000, 0.8) == pytest.approx(800 / 1609.344)
    assert miles_to_steps(steps_to_miles(12345, 0.75), 0.75) == pytest.approx(12345)


def test_chapter_fraction(quest):
    # Chapter A spans walkable 0..20; Chapter B spans 20..50 because the
    # boat stretch into its first waypoint belongs to it.
    assert quest.position(5).chapter_fraction == pytest.approx(0.25)
    assert quest.position(15).chapter_fraction == pytest.approx(0.75)
    assert quest.position(40).chapter_fraction == pytest.approx(20 / 30)
    assert quest.position(40).part_fraction == pytest.approx(40 / 50)


def test_chapter_switches_on_leaving_last_waypoint(quest):
    at_bucklebury = quest.position(20)
    assert at_bucklebury.reached.id == "bucklebury"
    assert at_bucklebury.chapter.title == "Chapter B"
    assert at_bucklebury.chapter_fraction == 0.0
    just_before = quest.position(19.99)
    assert just_before.chapter.title == "Chapter A"
    assert just_before.chapter_fraction == pytest.approx(19.99 / 20)


def test_default_path_points_at_bundled_frodo_file():
    path = Quest.default_path()
    assert path.name == "frodo.json"
    assert path.parent.name == "data"


def test_duplicate_ids_rejected(tmp_path):
    path = write_variant(tmp_path, lambda d: wp(d, 1).update(id="bag-end"))
    with pytest.raises(ValueError, match="duplicate waypoint id 'bag-end'"):
        load_quest(path)


def test_decreasing_road_miles_rejected(tmp_path):
    path = write_variant(tmp_path, lambda d: wp(d, 2).update(road_miles=5))
    with pytest.raises(ValueError, match="road_miles decreases at 'bucklebury'"):
        load_quest(path)


def test_unknown_mode_rejected(tmp_path):
    path = write_variant(tmp_path, lambda d: wp(d, 3).update(mode="eagle"))
    with pytest.raises(ValueError, match="unknown mode 'eagle' at 'far-bank'"):
        load_quest(path)
