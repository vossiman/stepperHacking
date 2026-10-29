import time
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from stepper_quests.journey_window import JourneyWindow
from stepper_quests.progress import Settings
from stepper_quests.quests import load_quest
from stepper_quests.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"


@pytest.fixture
def quest():
    return load_quest(FIXTURE)


@pytest.fixture
def store(home_dir):
    s = Store(Store.default_path())
    yield s
    s.close()


@pytest.fixture
def settings():
    return Settings(metres_per_step=0.7)


def test_window_renders_empty_store(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    w.refresh()
    assert "No walks yet" in w.walk_panel_text()
    assert w.current_tab() == "Journey"


def test_show_section_selects_tab(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    w.show_section("achievements")
    assert w.current_tab() == "Achievements"
    w.show_section("route")
    assert w.current_tab() == "Journey"


def _active_waypoint(w):
    return w.tree.findItems("▶", Qt.MatchContains | Qt.MatchRecursive)[-1]


def _in_view(w, item):
    rect = w.tree.visualItemRect(item)
    return not rect.isEmpty() and w.tree.viewport().rect().contains(rect)


def test_route_section_centres_active_waypoint(store, quest, settings, qapp):
    w = JourneyWindow(store, quest, settings)
    w.tree.setMaximumHeight(50)
    w.show()
    qapp.processEvents()
    w.tree.topLevelItem(0).setExpanded(False)
    w.tree.verticalScrollBar().setValue(0)
    assert not _in_view(w, _active_waypoint(w))
    w.show_section("route")
    qapp.processEvents()
    assert w.tree.topLevelItem(0).isExpanded()
    assert _in_view(w, _active_waypoint(w))


def test_new_active_chapter_is_expanded(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    w.tree.collapseAll()
    store.upsert_session(None, time.time() - 7200, time.time() - 3600, 50000.0, 100, 90.0, 3000.0)
    w.refresh()
    [chapter] = w.tree.findItems("Chapter B", Qt.MatchContains | Qt.MatchRecursive)
    assert chapter.isExpanded()
    assert chapter.parent().isExpanded() and chapter.parent().parent().isExpanded()


def test_refresh_keeps_tab_and_expansion(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    w.show_section("achievements")
    top = w.tree.topLevelItem(0)
    top.setExpanded(False)
    w.refresh()
    assert w.current_tab() == "Achievements"
    assert not w.tree.topLevelItem(0).isExpanded()


def test_tab_is_remembered(store, quest, settings):
    JourneyWindow(store, quest, settings).show_section("achievements")
    assert JourneyWindow(store, quest, settings).current_tab() == "Achievements"


def test_live_walk_panel(store, quest, settings):
    store.upsert_session(None, time.time() - 120, None, 80.0, 70, 66.0, 100.0)
    w = JourneyWindow(store, quest, settings)
    assert "Walking now" in w.walk_panel_text()


def test_walk_panel_caps_reached_names(store, quest, settings):
    start = time.time() - 600
    store.upsert_session(None, start, None, 100.0, 70, 66.0, 100.0)
    for w in quest.waypoints[:5]:
        store.mark_waypoint(quest.id, w.id, start + 10)
    text = JourneyWindow(store, quest, settings).walk_panel_text()
    names = [w.name for w in quest.waypoints[:5]]
    assert "and 2 more" in text
    assert sum(name in text for name in names) == 3
