from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from stepper_quests import journey_model as jm
from stepper_quests.quests import load_quest
from stepper_quests.route_widget import PHASE_STEP, RouteWidget

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"


@pytest.fixture
def quest():
    return load_quest(FIXTURE)


def test_paints_and_labels_reached_and_next(quest, qapp):
    w = RouteWidget(); w.resize(800, 200)
    pos = quest.position(5.0)
    w.set_span(jm.closeup_span(quest, pos), pos, 5.0, quest.drawn_markers(0.0, 10.0), "11,495 steps")
    w.grab()
    assert {"Bag End", "Hobbiton"} <= set(w.labelled_names())


def test_end_of_road_paints(quest, qapp):
    w = RouteWidget(); w.resize(800, 200)
    pos = quest.position(1000.0)
    w.set_span(jm.closeup_span(quest, pos), pos, 1000.0, [], None)
    w.grab()
    assert "Bree" in w.labelled_names()


def test_boat_leg_paints_mid_stride(quest, qapp):
    w = RouteWidget(); w.resize(800, 200)
    pos = quest.position(25.0)
    assert pos.next.mode == "boat"
    span = jm.closeup_span(quest, pos)
    w.set_span(span, pos, 25.0, quest.drawn_markers(span.start, span.end), "2,000 steps")
    w._tick()
    w.grab()
    assert {"Bucklebury", "Far Bank"} <= set(w.labelled_names())


def test_timer_runs_only_when_walking_and_visible(qapp):
    w = RouteWidget()
    w.set_walking(True)
    assert not w.is_animating()
    w.show(); assert w.is_animating()
    w.hide(); assert not w.is_animating()
    w.show(); w.set_walking(False); assert not w.is_animating()


def test_timer_tick_does_not_call_parent_refresh(quest, qapp):
    class Parent(QWidget):
        refreshes = 0

        def refresh(self):
            self.refreshes += 1

    parent = Parent()
    w = RouteWidget(parent)
    pos = quest.position(5.0)
    w.set_span(jm.closeup_span(quest, pos), pos, 5.0, [], "1 steps")
    w._timer.timeout.emit()
    w._timer.timeout.emit()
    assert parent.refreshes == 0
    assert w._phase == pytest.approx(2 * PHASE_STEP)


def test_timer_stops_while_window_minimized(qapp):
    window = QWidget()
    w = RouteWidget()
    QVBoxLayout(window).addWidget(w)
    w.set_walking(True)
    window.show()
    assert w.is_animating()
    window.setWindowState(Qt.WindowMinimized)
    assert not w.is_animating()
    window.setWindowState(Qt.WindowNoState)
    assert w.is_animating()
    window.close()
