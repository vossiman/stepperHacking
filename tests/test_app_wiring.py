"""Headless App wiring: cadence through the slot into the store, no BLE worker."""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from stepper_quests.app import App, AppSettings
from stepper_quests.frames_log import FrameLog
from stepper_quests.quests import load_quest
from stepper_quests.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "mini_quest.json"


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "steps.db"


@pytest.fixture
def app(tmp_path, db_path):
    store = Store(db_path)
    app = App(store, load_quest(FIXTURE), AppSettings(), use_ble=False,
              frame_log=FrameLog(tmp_path / "data"))
    yield app
    app.quit()
    app.deleteLater()


def walk(app, spm, start, seconds, step=0.5):
    t = start
    while t < start + seconds:
        app.on_cadence(spm, t)
        t += step


def rows(app):
    return app.store.all_sessions()


def t0():
    # Far enough back that the real-clock tick sees the walk as idle.
    return time.time() - 1000


def test_session_row_upserted_at_start(app):
    start = t0()
    app.on_cadence(60, start)
    [row] = rows(app)
    assert row["start"] == start
    assert row["end"] is None
    assert row["steps"] == 0


def test_running_steps_persisted_by_save(app):
    start = t0()
    walk(app, 60, start, 30)
    app._save_running()
    [row] = rows(app)
    assert row["steps"] == pytest.approx(29.5)
    assert row["end"] is None


def test_short_session_deleted_when_discarded(app):
    walk(app, 60, t0(), 5)
    assert len(rows(app)) == 1
    app._tick()
    assert rows(app) == []


def test_ended_session_row_has_end(app):
    start = t0()
    walk(app, 60, start, 30)
    app._tick()
    [row] = rows(app)
    assert row["end"] == start + 29.5
    assert row["steps"] == pytest.approx(29.5)


def test_icon_reconnecting_wins_over_stepping(app):
    walk(app, 60, t0(), 5)
    assert app.icon_state() == "stepping"
    app.on_ble_state("reconnecting")
    assert app.icon_state() == "reconnecting"
    app.on_ble_state("connected")
    assert app.icon_state() == "stepping"


def test_quit_ends_session_by_tracker_rules_and_records_achievements(app, db_path):
    earlier = (datetime.now() - timedelta(days=2)).timestamp()
    app.store.upsert_session(None, earlier, earlier + 60, 5.0, 60, 60.0, 60.0)
    start = time.time() - 40
    walk(app, 60, start, 30)
    app.quit()
    app.quit()
    store = Store(db_path)
    try:
        row = [r for r in store.all_sessions() if r["start"] == start][0]
        assert row["end"] == start + 29.5
        assert row["steps"] == pytest.approx(29.5)
        assert any(name.startswith("wander") for name, _, _ in store.unlocked())
    finally:
        store.close()


def test_quit_discards_short_session(app, db_path):
    walk(app, 60, time.time() - 10, 5)
    app.quit()
    store = Store(db_path)
    try:
        assert store.all_sessions() == []
    finally:
        store.close()


def test_apply_settings_toggles_frame_log_and_defers_idle_timeout(app, tmp_path):
    start = t0()
    walk(app, 60, start, 2)
    app.settings.log_frames = False
    app.settings.idle_timeout = 15
    app.apply_settings()
    assert app.tracker.idle_timeout == 60
    app.on_cadence(60, start + 2.5)
    assert app._frame_log._closed
    app._tick()
    walk(app, 60, time.time() - 100, 2)
    assert app.tracker.idle_timeout == 15
    assert app._frame_log._closed


def test_settings_dialog_stores_values_and_app_reapplies(app):
    app.open_settings()
    dialog = app._settings_dialog
    dialog.metres.setValue(0.85)
    dialog.idle.setValue(120)
    dialog.log_frames.setChecked(False)
    dialog.mac.setText("aa:bb:cc:dd:ee:ff")
    dialog.accept()
    assert app.store.get_setting("metres_per_step") == 0.85
    assert app.store.get_setting("idle_timeout") == 120
    assert app.store.get_setting("log_frames") is False
    assert app.store.get_setting("stepper_mac") == "AA:BB:CC:DD:EE:FF"
    assert app.settings.metres_per_step == 0.85
    assert app.tracker.idle_timeout == 120
    assert app.frame_log is None


def test_settings_dialog_rejects_bad_mac(app):
    app.open_settings()
    dialog = app._settings_dialog
    dialog.mac.setText("not a mac")
    dialog.accept()
    assert dialog.isVisible()
    assert app.store.get_setting("stepper_mac") is None
    dialog.reject()


def test_startup_repairs_crashed_sessions(tmp_path, db_path):
    store = Store(db_path)
    start = time.time() - 5000
    store.upsert_session(None, start, None, 0.0, 0, 0.0, 0.0)
    store.upsert_session(None, start + 100, None, 400.0, 60, 60.0, 400.0)
    app = App(store, load_quest(FIXTURE), AppSettings(), use_ble=False,
              frame_log=FrameLog(tmp_path / "data"))
    try:
        [row] = rows(app)
        assert row["steps"] == 400.0
        assert row["end"] == start + 500
    finally:
        app.quit()
        app.deleteLater()


class FakeWorker:
    def __init__(self, store):
        self.store = store
        self.calls = []

    def stop(self, timeout_ms=-1):
        self.calls.append((timeout_ms, [tuple(r) for r in self.store.all_sessions()]))
        return False


def test_quit_saves_session_before_stopping_worker_with_timeout(app):
    start = time.time() - 40
    walk(app, 60, start, 30)
    worker = app.worker = FakeWorker(app.store)
    app.quit()
    [(timeout, saved)] = worker.calls
    assert timeout == 3000
    [row] = saved
    assert row[2] == start + 29.5


def test_quit_notices_persist_and_toast_at_next_start(tmp_path, db_path, monkeypatch):
    store = Store(db_path)
    earlier = (datetime.now() - timedelta(days=2)).timestamp()
    store.upsert_session(None, earlier, earlier + 60, 25.0, 60, 60.0, 60.0)
    first = App(store, load_quest(FIXTURE), AppSettings(), use_ble=False,
                frame_log=FrameLog(tmp_path / "data"))
    walk(first, 60, time.time() - 40, 30)
    first.quit()
    first.deleteLater()

    store = Store(db_path)
    pending = store.get_setting("pending_notices")
    assert any(n["title"] == "Not all those who wander" for n in pending)
    shown = []
    monkeypatch.setattr(App, "_toast", lambda self, title, *a: shown.append(title))
    second = App(store, load_quest(FIXTURE), AppSettings(), use_ble=False,
                 frame_log=FrameLog(tmp_path / "data"))
    try:
        assert shown == []
        second.show_pending_notices()
        assert "Not all those who wander" in shown
        assert store.get_setting("pending_notices") == []
        second.show_pending_notices()
        assert shown.count("Not all those who wander") == 1
    finally:
        second.quit()
        second.deleteLater()


def test_open_journey_without_section_keeps_remembered_tab(app):
    app.store.set_setting("journey_tab", "Records")
    app.open_journey(None)
    assert app._journey.current_tab() == "Records"
    assert app.store.get_setting("journey_tab") == "Records"


def test_open_journey_with_section_selects_it(app):
    app.open_journey("achievements")
    assert app._journey.current_tab() == "Achievements"


def test_open_journey_saves_the_running_walk_first(app):
    start = t0()
    walk(app, 60, start, 30)
    app.open_journey(None)
    [row] = rows(app)
    assert row["steps"] == pytest.approx(29.5)


def test_open_journey_window_refreshes_on_session_end(app, monkeypatch):
    app.open_journey("route")
    calls = []
    monkeypatch.setattr(app._journey, "refresh", lambda: calls.append(1))
    walk(app, 60, t0(), 30)
    app._tick()
    assert calls
    app._journey.hide()
    calls.clear()
    walk(app, 60, t0() + 100, 30)
    app._tick()
    assert calls == []


@pytest.mark.parametrize(
    "argv, env, temp",
    [
        (["--demo"], {}, True),
        (["--demo-seed", "5000"], {}, True),
        (["--demo"], {"STEPPER_QUESTS_HOME": "/somewhere"}, False),
        ([], {}, False),
        (["--no-ble"], {}, False),
    ],
)
def test_demo_runs_use_a_temp_home(argv, env, temp):
    from stepper_quests.__main__ import parse_args
    from stepper_quests.app import demo_home

    home = demo_home(parse_args(argv), env)
    if temp:
        assert home.is_dir() and home.name.startswith("stepper-quests-demo-")
        home.rmdir()
    else:
        assert home is None


def test_progress_refresh_is_throttled(app):
    refreshed = []
    app._journey = type("W", (), {"isVisible": lambda s: True, "refresh": lambda s: refreshed.append(now[0])})()
    now = [0.0]
    app._clock = lambda: now[0]
    progress_times = []
    real_handle = app._handle

    def spy(events):
        if any(type(e).__name__ == "SessionProgress" for e in events):
            progress_times.append(now[0])
        real_handle(events)

    app._handle = spy
    start = t0()
    now[0] = start
    while now[0] < start + 6.0:
        app.on_cadence(70, now[0])
        now[0] += 0.5
    assert progress_times, "walk produced no progress events"
    expected, last = [], 0.0
    for t in progress_times:
        if t - last >= 1.0:
            expected.append(t)
            last = t
    assert len(expected) < len(progress_times)
    assert refreshed == expected


def test_no_mac_means_no_worker_and_a_hint(tmp_path, db_path):
    app = App(Store(db_path), load_quest(FIXTURE), AppSettings(stepper_mac=""), use_ble=True,
              frame_log=FrameLog(tmp_path / "data"))
    try:
        assert app.worker is None
        assert "no stepper MAC set" in app.tray.toolTip()
    finally:
        app.quit()
        app.deleteLater()
