# Stepper Quests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Cinnamon tray app that counts stepper steps over BLE automatically and maps the lifetime total onto Frodo's road with waypoints, toasts and achievements.

**Architecture:** Pure-Python core (protocol parser, step integrator, session state machine, SQLite store, quest position math, achievement rules) with unit tests, driven by a BLE worker thread (bleak, its own asyncio loop) that emits Qt signals into a PySide6 tray app (tray icon, toast widget, journey window, settings dialog). The quest content is a JSON data file, not code.

**Tech Stack:** Python 3.10+, bleak 3.x (already in `.venv`), PySide6 6.12 (installable from PyPI into `.venv`), sqlite3 (stdlib), pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-stepper-quests-design.md`

## Global Constraints

- Python package `stepper_quests/` at repo root; run as `.venv/bin/python -m stepper_quests`. Tests under `tests/`, run with `.venv/bin/python -m pytest`.
- Stepper MAC `AA:BB:CC:DD:EE:FF`; protocol exactly as `stepper.py` and README (init sequence, poll `f0a2010194` every 0.5 s, cadence = byte 9 of a `F0 B2` frame, raw value <= 1 means 0).
- Defaults: `metres_per_step` 0.7, `idle_timeout` 60 s, `min_session_steps` 20, `dt` cap 2.0 s, poll 0.5 s, reconnect backoff capped at 15 s.
- Travel ratios: foot 1, horse 3, boat 4, carried 1, eagle = free (no leg). Walkable miles = road miles / ratio. Steps to miles: `steps * metres_per_step / 1609.344`.
- Store at `~/.local/share/stepper-quests/steps.db` (override with env `STEPPER_QUESTS_HOME` for tests and dev).
- Tray icons are footprints, never a disc. App identity: `QApplication.setApplicationName("stepper-quests")`, `setDesktopFileName("stepper-quests")`; single instance via a `QLocalServer` named `stepper-quests`.
- No em dashes in any text (code, docs, toast copy).
- Commit after every task; conventional commit messages.

## Review Focus

1. A `F0 B2` frame shorter than 10 bytes (the `F0 B0 ...` 5-byte replies in the recordings) must parse as "not a metrics frame", never raise. Test in Task 2.
2. A wall-clock gap of minutes between two frames (reconnect) must add at most 2 s worth of steps. Test in Task 3.
3. A session that spans midnight is attributed to the day it started; today's steps and streaks use the start day. Test in Task 4.
4. Lifetime steps beyond the last waypoint: position reports the last waypoint as reached and `next_waypoint` is `None`, no IndexError. Test in Task 5.
5. Changing `metres_per_step` after waypoints were passed must not re-fire their toasts: waypoint toasts fire only on a transition observed during a session, and reached waypoints are recorded in the store. Test in Task 6.

---

### Task 1: Repository and package skeleton

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `requirements.txt` (modify: add `PySide6==6.12.0`, `pytest`), `stepper_quests/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

**Interfaces:**
- Produces: a git repo on branch `main` with the spec and plan committed; `.venv` has PySide6 and pytest; `STEPPER_QUESTS_HOME` fixture `home_dir(tmp_path, monkeypatch)` in conftest that sets the env var and returns the path.

- [ ] **Step 1:** `git init`, `.gitignore` with `.venv/`, `__pycache__/`, `data/`, `out/`, `*.db`, `.claude/worktrees/`.
- [ ] **Step 2:** `pyproject.toml` with `[tool.pytest.ini_options] testpaths=["tests"]`; `requirements.txt` adds `PySide6==6.12.0` and `pytest==8.3.3`; run `.venv/bin/pip install -r requirements.txt`.
- [ ] **Step 3:** Run `.venv/bin/python -c "import PySide6, bleak"` and `.venv/bin/python -m pytest` (expected: no tests ran, exit 5 is fine).
- [ ] **Step 4:** Commit: `chore: init repo with spec, plan and package skeleton` (include `README.md`, `stepper.py`, `docs/`).

### Task 2: Protocol module

**Files:**
- Create: `stepper_quests/protocol.py`, `tests/test_protocol.py`

**Interfaces:**
- Produces: `STEPPER_MAC = "AA:BB:CC:DD:EE:FF"`, `SVC_UUID`, `WRITE_UUID`, `NOTIFY_UUID`, `INIT_SEQUENCE: list[bytes]`, `POLL: bytes`, `POLL_INTERVAL = 0.5`, `checksum(body: bytes) -> int`, `parse_cadence(frame: bytes) -> int | None` (None for non-metrics or short frames; 0 when raw <= 1; else raw).

- [ ] **Step 1:** Write tests: `test_parse_cadence_from_recorded_frames` loads every `hex` column of `data/frames_20261029_121210.csv` (copy the first 40 rows into `tests/fixtures/frames.csv` so the test does not depend on gitignored data), asserts no exception and that at least one frame parses to a value between 50 and 70; `test_short_b0_frame_is_none` (`bytes.fromhex("f0b000c868")` -> None); `test_idle_raw_one_is_zero`; `test_checksum_matches_recorded_frames` (last byte equals `checksum(frame[:-1])` for every 19-byte B2 frame in the fixture); `test_init_sequence_matches_readme` (exact hex strings from README).
- [ ] **Step 2:** Run, expect ImportError.
- [ ] **Step 3:** Implement by moving the constants and logic out of `stepper.py` (leave `stepper.py` untouched; it stays as the calibration tool).
- [ ] **Step 4:** Run, expect PASS. Commit `feat: protocol parser with recorded-frame tests`.

### Task 3: Step integrator and session state machine

**Files:**
- Create: `stepper_quests/counter.py`, `tests/test_counter.py`

**Interfaces:**
- Produces:
  - `class StepIntegrator`: `feed(spm: int, t: float) -> float` returns steps added (`spm * min(dt, 2.0) / 60`, 0 on first frame); attribute `steps: float`.
  - `@dataclass Session`: `start: float`, `end: float | None`, `steps: float`, `max_spm: int`, `spm_sum: int`, `spm_n: int`, `active_seconds: float`; property `mean_spm`.
  - `class SessionTracker(idle_timeout=60.0, min_steps=20)`: `feed(spm: int, t: float) -> list[Event]`; `tick(t: float) -> list[Event]` (call with wall clock while disconnected); `current: Session | None`. Events are `SessionStarted(session)`, `SessionProgress(session)` (every feed while active), `SessionEnded(session, discarded: bool)`.
  - Rules: start on first `spm > 0`; end when `t - last_nonzero_t >= idle_timeout`; `end` is `last_nonzero_t`; discarded when `steps < min_steps`.

- [ ] **Step 1:** Tests: `test_integrates_steady_cadence` (60 spm, frames every 0.5 s for 60 s -> ~60 steps, tolerance 1); `test_gap_capped_at_two_seconds` (frame at t=0 then t=600 at 60 spm -> added steps == 2.0); `test_session_starts_on_first_nonzero`; `test_session_ends_after_idle_timeout_via_tick`; `test_short_session_discarded`; `test_session_survives_gap` (frames, then no frames for 30 s, `tick(30)`, then frames: same session, one SessionStarted only); `test_end_time_is_last_nonzero`.
- [ ] **Step 2:** Run, expect fail. **Step 3:** Implement. **Step 4:** Run, PASS. Commit `feat: step integrator and session tracker`.

### Task 4: SQLite store

**Files:**
- Create: `stepper_quests/store.py`, `tests/test_store.py`

**Interfaces:**
- Produces `class Store(path: Path)` with: `upsert_session(session_id: int | None, start: float, end: float | None, steps: float, max_spm: int, mean_spm: float, active_seconds: float) -> int`; `delete_session(id)`; `lifetime_steps() -> float`; `steps_on_day(date) -> float`; `sessions_on_day(date) -> list[Row]`; `best_day() -> tuple[date, float] | None`; `longest_session_steps() -> float`; `streak_days(today: date) -> int` (consecutive days ending today or yesterday with a session, start-day attribution); `get_setting(key, default)`, `set_setting(key, value)` (JSON-encoded); `unlock(name, at: float, note: str = "") -> bool` (False if already unlocked and not repeatable), `unlocked() -> list[(name, at, note)]`; `mark_waypoint(quest_id, waypoint_id, at)`, `reached_waypoints(quest_id) -> set[str]`. `Store.default_path()` honours `STEPPER_QUESTS_HOME`. Local time via `datetime.fromtimestamp`.

- [ ] **Step 1:** Tests for each query including `test_session_over_midnight_counts_for_start_day`, `test_streak_counts_consecutive_days`, `test_streak_broken_by_gap`, `test_lifetime_is_sum_of_sessions`, `test_unlock_twice_returns_false`.
- [ ] **Step 2 to 4:** fail, implement (schema created in `__init__`, WAL mode), pass. Commit `feat: sqlite store`.

### Task 5: Quest model and position math

**Files:**
- Create: `stepper_quests/quests.py`, `tests/test_quests.py`, `tests/fixtures/mini_quest.json`

**Interfaces:**
- Quest JSON schema: `{"id": "frodo", "title": ..., "ratios": {"foot":1,"horse":3,"boat":4,"carried":1}, "volumes": [{"title": ..., "parts": [{"title": ..., "chapters": [{"title": ..., "leg": ..., "waypoints": [{"id": ..., "name": ..., "road_miles": <cumulative from Bag End>, "mode": "foot", "story": ...}]}]}]}]}`. The first waypoint of the whole quest is Bag End at 0. A waypoint's `mode` is the mode of the stretch ending at it.
- Produces: `load_quest(path) -> Quest`; `Quest.waypoints -> list[Waypoint]` flattened in order, each with `walkable_miles` cumulative (computed from road-mile deltas divided by the ratio) and back-references `chapter`, `part`, `volume`; `Quest.total_walkable_miles`; `steps_to_miles(steps, metres_per_step) -> float`; `miles_to_steps(miles, metres_per_step) -> float`; `Quest.position(walkable_miles) -> Position` with `reached: Waypoint` (last with `walkable_miles <= x`), `next: Waypoint | None`, `fraction_to_next`, `chapter_fraction`, `part_fraction`, `miles_to_next`.

- [ ] **Step 1:** Fixture quest with 2 chapters, 5 waypoints, one boat stretch. Tests: `test_walkable_miles_apply_ratio` (boat stretch of 40 road miles adds 10), `test_position_mid_leg`, `test_position_past_end_has_no_next`, `test_steps_miles_roundtrip`, `test_chapter_fraction`.
- [ ] **Step 2 to 4.** Commit `feat: quest model and position math`.

### Task 6: Achievements and progress events

**Files:**
- Create: `stepper_quests/progress.py`, `tests/test_progress.py`

**Interfaces:**
- Consumes Store, Quest, SessionTracker events.
- Produces `class Progress(store, quest, settings)` with `on_session_progress(session) -> list[Notice]` and `on_session_ended(session) -> list[Notice]`. `Notice(kind: "waypoint"|"achievement"|"part", title: str, body: str)`.
  - Waypoints: compare `reached_waypoints` in store with the quest position at current lifetime steps (store lifetime + running session steps); every newly reached waypoint is marked in the store and yields a Notice with its name and story. On first run, waypoints already behind the marker are marked silently (no toasts) via `Progress.sync_silently()` called at startup.
  - Achievements (names and rules from the spec): Second Breakfast, Elevenses, Hobbit's Pace (7), Rangers of the North (30), Long-expected Party (100000), Sting Glows (repeatable, note = new best), Not all those who wander (repeatable, note = steps), The Road Goes Ever On (repeatable per part, note = part title). Evaluated in `on_session_ended`.

- [ ] **Step 1:** Tests with a temp store and the mini quest: `test_waypoint_notice_once`, `test_sync_silently_marks_without_notices`, `test_metres_per_step_change_does_not_refire` (mark at 0.7, change to 1.0, call progress: no waypoint notice for already marked), `test_second_breakfast_needs_two_hours`, `test_streak_seven`, `test_best_day_repeatable_with_note`, `test_part_completed_notice`.
- [ ] **Step 2 to 4.** Commit `feat: waypoint and achievement progress`.

### Task 7: Frodo's road quest data

**Files:**
- Create: `stepper_quests/data/frodo.json`, `stepper_quests/data/SOURCES.md`, `tests/test_frodo_data.py`

**Interfaces:**
- Consumes the schema from Task 5. Produces the real quest file loaded by default (`Quest.default_path()`).

- [ ] **Step 1:** Research: fetch the Eowyn Challenge waypoint tables (search for "Eowyn Challenge" "Walk to Rivendell" milestones; mirrors such as under1000skies.org and fan blogs carry the day-by-day table). Record URLs and retrieval date in `SOURCES.md`. Stage totals to match within 5 percent: Bag End to Rivendell 458, to Lothlórien +462, to Rauros +389, to Mount Doom +470 road miles.
- [ ] **Step 2:** Write `frodo.json`: volumes The Fellowship of the Ring (Part 1, Part 2), The Two Towers (Part 2, Frodo and Sam), The Return of the King (Part 2, Frodo and Sam); chapters titled with Tolkien's chapter titles; waypoints every 2 to 4 road miles on foot legs using named places (add named places from the books where the table is coarse), only named places on the boat and horse stretches. Modes per the spec's rule: everything foot except the Asfaloth gallop to the Ford (horse) and Lórien to Rauros (boat); Sam carrying Frodo on Mount Doom is `carried`. Every waypoint has a one or two sentence `story` in own words.
- [ ] **Step 3:** Tests: `test_loads`, `test_miles_monotonic`, `test_stage_totals` (Rivendell 458 +-5%, Mount Doom total 1779 +-5%), `test_foot_gaps_at_most_four_miles` (allow up to 6 for at most 5 stretches), `test_every_waypoint_has_story`, `test_modes_valid`.
- [ ] **Step 4:** Run, PASS. Commit `feat: Frodo's road quest data`.

### Task 8: BLE worker thread

**Files:**
- Create: `stepper_quests/ble.py`, `tests/test_ble.py`

**Interfaces:**
- Produces `class BleWorker(QThread)` with signals `state_changed(str)` (`"disconnected"|"connecting"|"connected"`), `cadence(int, float)` (spm, wall time), `log(str)`; `stop()`. Internally runs an asyncio loop: connect by MAC with `BleakClient(address)`, `start_notify`, init sequence, poll loop; on any exception emit `disconnected`, sleep backoff (1, 2, 4, 8, 15, 15, ...), retry forever until `stop()`. The connect/poll logic lives in a plain async function `run_session(client_factory, on_cadence, on_state, stop_event)` so it is testable without Qt or hardware.
- Also: `stepper_quests/frames_log.py` with `FrameLog(dir)` writing `frames_*.csv` and `steps_*.csv` like `stepper.py`, enabled by setting `log_frames` (default True), directory `data/` under `STEPPER_QUESTS_HOME`.

- [ ] **Step 1:** Test `run_session` with a fake client (records writes, emits recorded B2 frames on a timer, raises on the Nth poll): `test_init_then_poll_sequence`, `test_cadence_emitted`, `test_exception_leads_to_disconnected_and_retry`, `test_backoff_sequence`.
- [ ] **Step 2 to 4.** Commit `feat: BLE worker with reconnect loop`.

### Task 9: Tray, toast and application wiring

**Files:**
- Create: `stepper_quests/icons.py` (footprint SVG strings per state, `make_icon(state) -> QIcon` rendered via QSvgRenderer at 22 and 48 px), `stepper_quests/toast.py`, `stepper_quests/app.py`, `stepper_quests/__main__.py`
- Create: `tests/test_icons.py` (offscreen: `QT_QPA_PLATFORM=offscreen`; icons are non-null and differ per state)

**Interfaces:**
- `Toast(QWidget)`: frameless, `Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`, bottom-right of primary screen with 16 px margin, `show_notice(title, body, seconds, on_click)`; stacks newest on top if several; fades out.
- `App`: builds `QApplication` (identity per Global Constraints), single-instance guard, `Store`, `Quest`, `SessionTracker`, `Progress`, `BleWorker`; a 1 s `QTimer` calls `tracker.tick(time.time())`; writes the running session to the store every 10 s; tray icon state from worker state plus tracker activity; tooltip "stepping, 62 spm, 1,812 today" style; menu: Open journey window, (disabled) Today / Lifetime rows, Quests..., Settings..., Quit. Toast copy per spec: start "Leaving {reached}. {n} steps to {next}.", end "{steps} steps in {min} min. {next} is {n} steps away."
- Journey window and settings dialog are stubs here (empty QDialog) and filled in Tasks 10 and 11.

- [ ] **Step 1:** Icon test, run offscreen. **Step 2:** Implement all. **Step 3:** Manual check: `DISPLAY=:0 .venv/bin/python -m stepper_quests --no-ble --demo` where `--demo` feeds a scripted cadence (20 s at 60 spm then zero) so the tray, toasts and session end can be seen without hardware; verify a start toast, an end toast and the icon change, then quit from the menu. Capture a screenshot of the toast with `import` or `gnome-screenshot` into `out/` if available.
- [ ] **Step 4:** Commit `feat: tray app with toasts and demo mode`.

### Task 10: Journey window

**Files:**
- Create: `stepper_quests/journey_window.py`, `stepper_quests/route_widget.py`; modify `app.py` to open it.

**Interfaces:**
- `JourneyWindow(store, quest, settings)` with `refresh()` and `show_section(name)` (`"route"|"achievements"`). Layout per spec and mockup: breadcrumb, current leg, `RouteWidget` (QPainter: waypoints of the active part on a gently curved line, done segment solid, ahead dashed, marker; names below alternating above/below to avoid overlap), six tiles (next waypoint steps, chapter %, part %, today, lifetime with km and road miles, best day), then the quest list (QTreeWidget: volume > part > chapter, chapter rows show miles, steps, days at current pace; active chapter expanded to waypoints with done/active/ahead markers), then an Achievements section (unlocked with date, locked greyed with condition).
- Pace for day estimates: mean steps per active day over the last 30 days, falling back to 1,740.

- [ ] **Step 1:** Implement. **Step 2:** Manual check in demo mode with a store seeded by `--demo-seed 88402` (lifetime steps), screenshot into `out/`. **Step 3:** Commit `feat: journey window`.

### Task 11: Settings, autostart and launcher

**Files:**
- Create: `stepper_quests/settings_dialog.py`, `stepper-quests.desktop`, `bin/stepper-quests` (shell launcher: `cd` to repo root, `exec setsid .venv/bin/python -m stepper_quests "$@"`), `README.md` section "Tray app".

**Interfaces:**
- Settings: metres per step (0.4 to 1.2, help text says changing it moves the marker), idle timeout seconds, log frames on/off, stepper MAC. Stored via `Store.set_setting`; app re-reads on dialog accept.
- Desktop file modelled on an existing autostart entry with `Exec=<repo>/bin/stepper-quests`, `Name=Stepper Quests`, `Icon=` pointing at an SVG written to `stepper_quests/data/icon.svg`. Install step: copy to `~/.config/autostart/` (document the command in README; do it in this task).

- [ ] **Step 1:** Implement dialog and files. **Step 2:** `desktop-file-validate stepper-quests.desktop` if available; launch via `bin/stepper-quests` from another directory and confirm it runs (log line) and the tray appears; quit. **Step 3:** Commit `feat: settings dialog, launcher and autostart`.

### Task 12: Hardware run and handover

- [ ] **Step 1:** Launch `bin/stepper-quests` with the stepper powered. Confirm the log shows connect, init, cadence frames when the owner steps (the owner must step; if nobody is available, verify connect and idle only and say so).
- [ ] **Step 2:** Check CPU with `top -b -n 1 -p <pid>` while idle and connected: expect under 2 percent.
- [ ] **Step 3:** Update README (quick start for the tray app, demo mode, where the db lives). Commit `docs: tray app usage`.
- [ ] **Step 4:** Report what was verified on hardware and what was not.
