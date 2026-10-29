"""Tray application: wires BLE cadence through the tracker into the store and toasts."""

import logging
import os
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import copy
from .ble import BleWorker
from .counter import Session, SessionEnded, SessionProgress, SessionStarted, SessionTracker
from .frames_log import FrameLog
from .icons import STATES, make_icon
from .journey_window import JourneyWindow
from .progress import Notice, Progress, notices_from_json, notices_to_json
from .protocol import STEPPER_MAC
from .quests import Quest, load_quest, steps_to_miles
from .settings_dialog import SettingsDialog
from .store import Store
from .toast import ToastManager

log = logging.getLogger("stepper_quests")

INSTANCE_NAME = "stepper-quests"
MIN_SESSION_STEPS = 20
PENDING_NOTICES = "pending_notices"
PENDING_DELAY_MS = 2000
WORKER_STOP_MS = 3000
TICK_MS = 1000
SAVE_MS = 10_000
SESSION_TOAST_S = 5
NOTICE_TOAST_S = 8
DEMO_FRAME_S = 0.5
DEMO_WALK_S = 30.0
DEMO_SPM = 60


@dataclass
class AppSettings:
    metres_per_step: float = 0.7
    idle_timeout: float = 60.0
    log_frames: bool = True
    stepper_mac: str = STEPPER_MAC

    @classmethod
    def load(cls, store: Store) -> "AppSettings":
        d = cls()
        return cls(
            metres_per_step=float(store.get_setting("metres_per_step", d.metres_per_step)),
            idle_timeout=float(store.get_setting("idle_timeout", d.idle_timeout)),
            log_frames=bool(store.get_setting("log_frames", d.log_frames)),
            stepper_mac=str(store.get_setting("stepper_mac", d.stepper_mac)),
        )


class App(QObject):
    def __init__(self, store: Store, quest: Quest, settings: AppSettings,
                 *, use_ble: bool = True, frame_log: FrameLog | None = None):
        super().__init__()
        self.store = store
        self.quest = quest
        self.settings = settings
        self._frame_log = frame_log
        repaired = store.repair_sessions(MIN_SESSION_STEPS)
        if repaired:
            log.info("repaired %d session rows left by a crash", repaired)
        self.tracker = SessionTracker(settings.idle_timeout, MIN_SESSION_STEPS)
        self.progress = Progress(store, quest, settings)
        self.progress.sync_silently()
        self._pending = notices_from_json(store.get_setting(PENDING_NOTICES))

        self._session_id: int | None = None
        self._persisted_steps = 0.0
        self._spm = 0
        self._ble_state = "connecting" if use_ble else "connected"
        self._icons = {state: make_icon(state) for state in STATES}
        self._icon_state: str | None = None
        self._journey: JourneyWindow | None = None
        self._clock = time.time
        self._last_journey_refresh = 0.0
        self._settings_dialog: SettingsDialog | None = None
        self._quitting = False
        self.toasts = ToastManager()

        if frame_log is not None:
            # Raw frames are kept per walking session, not for idle hours.
            frame_log.close()

        self._build_tray()

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(TICK_MS)
        self._save_timer = QTimer(self)
        self._save_timer.timeout.connect(self._save_running)
        self._save_timer.start(SAVE_MS)

        self.worker = None
        if use_ble and not settings.stepper_mac:
            log.warning("no stepper MAC set; open Settings... in the tray menu")
            self._ble_state = "unconfigured"
        elif use_ble:
            self.worker = BleWorker(settings.stepper_mac, frame_log, parent=self)
            self.worker.state_changed.connect(self.on_ble_state, Qt.QueuedConnection)
            self.worker.cadence.connect(self.on_cadence, Qt.QueuedConnection)
            self.worker.log.connect(lambda msg: log.info("ble: %s", msg), Qt.QueuedConnection)
            self.worker.start()

        self._refresh()
        if self._pending:
            QTimer.singleShot(PENDING_DELAY_MS, self, self.show_pending_notices)

    def show_pending_notices(self) -> None:
        """Toast notices earned during the last quit, once the tray is up."""
        if self._quitting or not self._pending:
            return
        notices, self._pending = self._pending, []
        self.store.set_setting(PENDING_NOTICES, [])
        self._notify(notices)

    # tray

    def _build_tray(self) -> None:
        self._icon_state = self.icon_state()
        self.tray = QSystemTrayIcon(self._icons[self._icon_state], self)
        menu = QMenu()
        menu.addAction("Open journey window", lambda: self.open_journey(None))
        menu.addSeparator()
        self._today_action = menu.addAction("Today: 0 steps")
        self._today_action.setEnabled(False)
        self._lifetime_action = menu.addAction("Lifetime: 0 steps")
        self._lifetime_action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Settings...", self.open_settings)
        menu.addAction("Quit", self.quit)
        menu.aboutToShow.connect(self._refresh)
        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.open_journey(None)

    def _unpersisted_steps(self) -> float:
        current = self.tracker.current
        return current.steps - self._persisted_steps if current is not None else 0.0

    def icon_state(self) -> str:
        if self._ble_state != "connected":
            return "reconnecting"
        if self.tracker.current is not None:
            return "stepping"
        return "idle"

    def _refresh(self) -> None:
        state = self.icon_state()
        if state != self._icon_state:
            self._icon_state = state
            self.tray.setIcon(self._icons[state])
            log.info("tray: %s", state)
        today = self.store.steps_on_day(date.today()) + self._unpersisted_steps()
        lifetime = self.store.lifetime_steps() + self._unpersisted_steps()
        tip_state = "unconfigured" if self._ble_state == "unconfigured" else state
        self.tray.setToolTip(copy.tooltip(tip_state, self._spm, today))
        self._today_action.setText(f"Today: {copy.format_steps(today)} steps")
        self._lifetime_action.setText(f"Lifetime: {copy.format_steps(lifetime)} steps")

    # BLE and tracker

    @property
    def frame_log(self) -> FrameLog | None:
        return self._frame_log if self.settings.log_frames else None

    @Slot(str)
    def on_ble_state(self, state: str) -> None:
        if self._quitting:
            return
        log.info("ble state: %s", state)
        self._ble_state = state
        if state != "connected":
            self._spm = 0
        self._refresh()

    @Slot(int, float)
    def on_cadence(self, spm: int, t: float) -> None:
        if self._quitting:
            return
        self._spm = spm
        events = self.tracker.feed(spm, t)
        current = self.tracker.current
        if self.frame_log is not None and current is not None:
            self.frame_log.write_step(t, spm, int(current.steps))
        self._handle(events)

    def _tick(self) -> None:
        if self._quitting:
            return
        self._handle(self.tracker.tick(time.time()))
        self._refresh()

    def _handle(self, events) -> None:
        for event in events:
            if isinstance(event, SessionStarted):
                self._session_started(event.session)
            elif isinstance(event, SessionProgress):
                self._notify(self.progress.on_session_progress(self._unpersisted_steps()))
                if self._clock() - self._last_journey_refresh >= 1.0:
                    self._refresh_journey()
            elif isinstance(event, SessionEnded):
                self._session_ended(event.session, event.discarded)
        if events:
            self._refresh()

    def _position(self, extra_steps: float = 0.0):
        lifetime = self.store.lifetime_steps() + extra_steps
        return self.quest.position(steps_to_miles(lifetime, self.settings.metres_per_step))

    def _session_started(self, session: Session) -> None:
        log.info("session started")
        self.tracker.idle_timeout = self.settings.idle_timeout
        if self.frame_log is not None:
            self.frame_log.open_session()
        self._session_id = self.store.upsert_session(None, session.start, None, 0.0, 0, 0.0, 0.0)
        self._persisted_steps = 0.0
        body = copy.start_message(self._position(), self.settings.metres_per_step)
        self._toast("On the road", body, SESSION_TOAST_S, "route")

    def _save_running(self) -> None:
        session = self.tracker.current
        if session is None or self._session_id is None:
            return
        self._upsert(session)

    def _upsert(self, session: Session) -> None:
        self.store.upsert_session(
            self._session_id, session.start, session.end, session.steps,
            session.max_spm, session.mean_spm, session.active_seconds,
        )
        self._persisted_steps = session.steps

    def _session_ended(self, session: Session, discarded: bool, *, announce: bool = True) -> None:
        log.info("session ended: %.0f steps%s", session.steps, " (discarded)" if discarded else "")
        if self._frame_log is not None:
            self._frame_log.close()
        self._spm = 0
        if self._session_id is not None:
            if discarded:
                self.store.delete_session(self._session_id)
            else:
                self._upsert(session)
        self._session_id = None
        self._persisted_steps = 0.0
        if discarded:
            return
        notices = self.progress.on_session_ended(session)
        if not announce:
            if notices:
                pending = notices_from_json(self.store.get_setting(PENDING_NOTICES)) + notices
                self.store.set_setting(PENDING_NOTICES, notices_to_json(pending))
            return
        body = copy.end_message(session, self._position(), self.settings.metres_per_step)
        self._toast("Rest stop", body, SESSION_TOAST_S, "route")
        self._notify(notices)
        self._refresh_journey()

    def _notify(self, notices: list[Notice]) -> None:
        for notice in notices:
            section = "achievements" if notice.kind == "achievement" else "route"
            self._toast(notice.title, notice.body, NOTICE_TOAST_S, section)
        if notices:
            self._refresh_journey()

    def _refresh_journey(self) -> None:
        if self._journey is not None and self._journey.isVisible():
            self._save_running()
            self._journey.refresh()
            self._last_journey_refresh = self._clock()

    def _toast(self, title: str, body: str, seconds: float, section: str) -> None:
        log.info("toast: %s: %s", title, body)
        self.toasts.show_notice(title, body, seconds, lambda: self.open_journey(section))

    # windows

    def open_journey(self, section: str | None) -> None:
        """Open the journey window; ``None`` keeps its remembered tab."""
        if self._journey is None:
            self._journey = JourneyWindow(self.store, self.quest, self.settings)
        self._save_running()
        self._journey.refresh()
        if section is not None:
            self._journey.show_section(section)
        self._journey.show()
        self._journey.raise_()
        self._journey.activateWindow()

    def open_settings(self) -> None:
        if self._settings_dialog is None or not self._settings_dialog.isVisible():
            self._settings_dialog = SettingsDialog(self.settings, self.store)
            self._settings_dialog.accepted.connect(self.apply_settings)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def apply_settings(self) -> None:
        """Re-read the live settings after the dialog stored them.

        The idle timeout is picked up when the next session starts; the MAC
        only on restart, because the BLE worker holds its own address.
        """
        log.info("settings applied: %s", self.settings)
        if self.tracker.current is None:
            self.tracker.idle_timeout = self.settings.idle_timeout
        if self._frame_log is not None:
            if not self.settings.log_frames:
                self._frame_log.close()
            elif self.tracker.current is not None:
                self._frame_log.open_session()
        # A new stride length can move the marker past waypoints; mark them
        # silently instead of toasting a burst on the next frame.
        self.progress.sync_silently(self._unpersisted_steps())
        if self._journey is not None:
            self._journey.refresh()
        self._refresh()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        log.info("quitting")
        self._tick_timer.stop()
        self._save_timer.stop()
        # Save first: a slow BLE disconnect must not cost the walk at logout.
        for event in self.tracker.finish():
            self._session_ended(event.session, event.discarded, announce=False)
        if self._frame_log is not None:
            self._frame_log.close()
        if self.worker is not None and not self.worker.stop(WORKER_STOP_MS):
            log.warning("BLE worker did not stop within %d ms", WORKER_STOP_MS)
        self.toasts.close_all()
        self.tray.hide()
        self.store.close()
        QApplication.quit()


class DemoFeed(QObject):
    """Scripted cadence through the same slot as BLE: a walk, then standing still.

    Timestamps advance exactly one frame per tick from the start so the walk
    always integrates to DEMO_SPM * DEMO_WALK_S / 60 steps, whatever the
    timer jitter.
    """

    def __init__(self, app: App):
        super().__init__(app)
        self._app = app
        self._start = time.time()
        self._n = 0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._step)
        self._timer.start(int(DEMO_FRAME_S * 1000))
        self._step()

    def _step(self) -> None:
        elapsed = self._n * DEMO_FRAME_S
        spm = DEMO_SPM if elapsed <= DEMO_WALK_S else 0
        self._app.on_cadence(spm, self._start + elapsed)
        self._n += 1


def seed_store(store: Store, steps: int) -> None:
    if store.all_sessions():
        log.info("demo seed skipped: store is not empty")
        return
    yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())
    start = yesterday.replace(hour=12).timestamp()
    spm = 100
    seconds = steps / spm * 60
    store.upsert_session(None, start, start + seconds, float(steps), spm, float(spm), seconds)
    log.info("demo seed: %s steps dated yesterday", f"{steps:,}")


def demo_home(args, environ) -> Path | None:
    """A fresh temp dir for demo runs, so they never touch the real store."""
    if not (args.demo or args.demo_seed is not None) or environ.get("STEPPER_QUESTS_HOME"):
        return None
    return Path(tempfile.mkdtemp(prefix="stepper-quests-demo-"))


def _claim_single_instance() -> QLocalServer | None:
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_NAME)
    if probe.waitForConnected(300):
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    if not server.listen(INSTANCE_NAME):
        log.warning("single-instance server failed: %s", server.errorString())
    return server


def main(args) -> int:
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Identity is set before the QApplication exists so the portal sees it.
    QApplication.setApplicationName("stepper-quests")
    QApplication.setDesktopFileName("stepper-quests")
    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(make_icon("stepping"))

    server = _claim_single_instance()
    if server is None:
        print("already running")
        return 0

    quest_path = args.quest or Quest.default_path()
    if not quest_path.exists():
        print(f"stepper-quests: quest file not found: {quest_path}", file=sys.stderr)
        return 1
    try:
        quest = load_quest(quest_path)
    except (ValueError, KeyError) as exc:  # JSONDecodeError is a ValueError
        print(f"stepper-quests: bad quest file {quest_path}: {exc!r}", file=sys.stderr)
        return 1

    home = demo_home(args, os.environ)
    if home is not None:
        os.environ["STEPPER_QUESTS_HOME"] = str(home)
        log.info("demo run: using temporary data directory %s", home)
    store = Store(Store.default_path())
    if args.demo_seed is not None:
        seed_store(store, args.demo_seed)
    settings = AppSettings.load(store)
    if args.idle_timeout is not None:
        settings.idle_timeout = args.idle_timeout

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("no system tray available; toasts still work")

    use_ble = not (args.no_ble or args.demo)
    app = App(store, quest, settings, use_ble=use_ble,
              frame_log=FrameLog(FrameLog.default_dir()))
    qapp.aboutToQuit.connect(app.quit)

    def on_second_instance() -> None:
        socket = server.nextPendingConnection()
        if socket is not None:
            socket.close()
            socket.deleteLater()
        app.open_journey(None)

    server.newConnection.connect(on_second_instance)
    if args.demo:
        DemoFeed(app)

    for sig in (signal.SIGINT, signal.SIGTERM):
        # Python runs handlers between bytecodes, possibly mid-slot; quit from the loop.
        signal.signal(sig, lambda *_: QTimer.singleShot(0, app.quit))
    log.info("running: quest %s, ble %s", quest.title, "on" if use_ble else "off")
    return qapp.exec()
