# Journey Window Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-long-scroll journey window with a hero, two live panels and four tabs (Journey, Achievements, Records, History), as approved in the mockup.

**Architecture:** All numbers come from pure functions in `journey_model.py` (tested without Qt) backed by a few new `Store` queries. `journey_window.py` becomes layout only: hero, panels, a flat tab bar, and one widget per tab. A small `BarsWidget` paints the 7-day and 30-day strips. The app throttles a live refresh on session progress.

**Tech Stack:** Python 3.10+, PySide6 6.12, sqlite3, pytest with the offscreen `qapp` fixture in `tests/conftest.py`.

**Spec:** `docs/superpowers/specs/2026-10-29-journey-window-redesign.md`

## Global Constraints

- No em dashes anywhere (code, comments, commits, copy). Use `·` (U+00B7) as the separator in copy, as the existing breadcrumb does.
- Keep the existing palette and fonts from `journey_window.py` (`#1b1a17`, `#24221e`, brass `#d8b35a`, text `#e8e2d4`, muted `#8f8878`).
- `Store` is used from the main thread only; no new threads.
- Tests run with `.venv/bin/python -m pytest`; all 161 existing tests keep passing.
- Public signatures named in Interfaces blocks are binding; later tasks import them by those names.
- `date.today()` and `time.time()` are only called in `journey_window.py` and `app.py`; model functions take `today`/`now` parameters.

## Review Focus

1. A session that is open (`end IS NULL`) must show as "Walking now" with its partial steps, never as "Last walk" and never double counted in totals (Task 2: `latest_walk` test with an open row).
2. Week boundaries are Monday to Sunday in local time; a walk on Sunday 23:50 belongs to that week, Monday 00:10 to the next (Task 2: `week_stats` test).
3. A fresh database (no sessions) renders every panel and tab without exceptions and with the "none yet" copy (Task 4: `test_window_renders_empty_store`).
4. Refresh must not reset the selected tab, the tree expansion or the scroll position (Task 4: `test_refresh_keeps_tab_and_expansion`).
5. Progress-driven refresh must be throttled to one per second so a 0.5 s poll does not rebuild the tree twice a second (Task 5: `test_progress_refresh_is_throttled`).

---

### Task 1: Store queries for sessions and reached waypoints

**Files:**
- Modify: `stepper_quests/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces:
  - `Store.open_session() -> sqlite3.Row | None` (the row with `end IS NULL`, newest start if several)
  - `Store.last_session() -> sqlite3.Row | None` (newest by start among rows with `end IS NOT NULL`)
  - `Store.first_session_start() -> float | None`
  - `Store.waypoints_reached_between(quest_id: str, lo: float, hi: float) -> list[str]` (waypoint ids with `lo <= at <= hi`, ordered by `at`)
  - `Store.sessions_between(lo: float, hi: float) -> list[sqlite3.Row]` (`lo <= start < hi`, ordered by start)

- [ ] **Step 1: Write failing tests** in `tests/test_store.py`

```python
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
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_store.py -v` and see the four new tests fail with `AttributeError`.
- [ ] **Step 3: Implement** the five methods in `stepper_quests/store.py` next to `sessions_on_day`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_store.py -v`, all pass.
- [ ] **Step 5: Commit** `feat(store): session and waypoint lookups for the journey window`

---

### Task 2: Journey model numbers

**Files:**
- Modify: `stepper_quests/journey_model.py`
- Test: `tests/test_journey_model.py`

**Interfaces:**
- Consumes: Task 1 store methods; existing `pace_steps_per_day`, `road_miles_walked`, `today_stats`, `Quest`, `Position`, `miles_to_steps`, `format_steps`.
- Produces (all in `journey_model.py`):

```python
def duration_text(days: float) -> str
    # < 60 days: "N days" (round, min 1, "1 day"); < 730 days: "N months" (round(days/30.4375));
    # else "N years M months" with " M months" dropped when M == 0.

def projection_line(quest: Quest, position: Position, metres_per_step: float,
                    pace: float | None) -> str
    # "1,779 road miles to the Crack of Doom. About 4 years at your pace."
    # pace None -> "... Your first walk sets the pace."
    # road miles left = quest.waypoints[-1].road_miles - road_miles_walked(position), rounded to int
    # days = miles_to_steps(walkable miles left, mps) / pace
    # At the end (position.next is None): "You stand at the Crack of Doom."

@dataclass(frozen=True)
class WalkSummary:
    live: bool            # True when the row is the open session
    start: float
    steps: float
    minutes: float
    mean_spm: float
    max_spm: int
    reached: list[str]    # waypoint names reached during the walk

def latest_walk(store: Store, quest: Quest) -> WalkSummary | None
    # open_session() first, else last_session(); reached via waypoints_reached_between
    # (hi = end, or 1e12 when open) mapped to names through quest.waypoints by id.

def start_pill(start: float, today: date) -> str
    # "today 14:33", "yesterday 09:10", else "Mon 27 Oct"

@dataclass(frozen=True)
class WeekStats:
    last7: list[float]          # steps per day, oldest first, ends today
    labels: list[str]           # weekday initials for last7 ("M","T","W","T","F","S","S")
    this_week: float            # Monday of today's week .. today
    last_week: float            # previous Monday .. Sunday
    best_day: tuple[date, float] | None   # within last7, None when all zero

def week_stats(store: Store, today: date) -> WeekStats

def week_line(w: WeekStats) -> str
    # "This week 2,140 steps · last week 3,800 · best day 1,520 (Sat)"; drop the best-day clause when None

@dataclass(frozen=True)
class Records:
    records: list[tuple[str, str]]   # the Records column, label/value, in spec order
    totals: list[tuple[str, str]]
    pace: list[tuple[str, str]]

def records(store: Store, quest: Quest, position: Position, metres_per_step: float,
            today: date) -> Records
    # Values exactly as the spec lists them. Rivendell and Mount Doom targets are the
    # waypoints whose name starts with "Rivendell" and the last waypoint of the quest;
    # when a target is already passed the value is "reached". "Frodo's pace" is
    # f"you are at {road_miles_walked/total_road_miles:.1%} of his 6 months".
    # Fallbacks with no sessions: "none yet" for records and pace rows, "0" for counts.

@dataclass(frozen=True)
class DayRow:
    day: date
    steps: float
    walks: int
    minutes: float
    mean_spm: float
    reached: list[str]

def history_days(store: Store, quest: Quest, today: date, days: int = 30) -> list[DayRow]
    # newest first; only days >= date of first_session_start(); [] with no sessions

def walking_days_text(rows: list[DayRow]) -> str
    # "Last 30 days. Walking days 14 of 30." (denominator = len(rows))
```

- [ ] **Step 1: Write failing tests** in `tests/test_journey_model.py` using the existing `store` and `quest` fixtures there (mini quest). At minimum:

```python
def test_duration_text():
    assert jm.duration_text(0.2) == "1 day"
    assert jm.duration_text(14.4) == "14 days"
    assert jm.duration_text(90) == "3 months"
    assert jm.duration_text(365.25 * 4) == "4 years"
    assert jm.duration_text(365.25 * 4 + 61) == "4 years 2 months"


def test_projection_line_without_pace(quest):
    pos = quest.position(0.0)
    assert jm.projection_line(quest, pos, 0.7, None).endswith("Your first walk sets the pace.")


def test_latest_walk_prefers_open_session(store, quest):
    store.upsert_session(None, 1000.0, 1300.0, 200.0, 70, 65.0, 300.0)
    store.upsert_session(None, 2000.0, None, 50.0, 60, 60.0, 40.0)
    w = jm.latest_walk(store, quest)
    assert w.live and w.steps == 50.0


def test_latest_walk_names_reached_waypoints(store, quest):
    store.upsert_session(None, 1000.0, 1300.0, 200.0, 70, 65.0, 300.0)
    store.mark_waypoint(quest.id, quest.waypoints[0].id, 1100.0)
    assert jm.latest_walk(store, quest).reached == [quest.waypoints[0].name]


def test_week_stats_boundaries(store):
    # today is Wednesday 2026-10-28; Sunday 23:50 counts last week, Monday 00:10 this week
    ...  # upsert sessions at those timestamps, assert this_week/last_week, labels end with "W"


def test_records_empty(store, quest):
    r = jm.records(store, quest, quest.position(0.0), 0.7, date(2026, 10, 28))
    assert dict(r.records)["Best day"] == "none yet"
    assert dict(r.totals)["Walks"] == "0"


def test_history_days_starts_at_first_session(store, quest):
    ...  # two sessions, 3 days apart; expect 4 rows newest first, zero rows in between
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_journey_model.py -v`, new tests fail.
- [ ] **Step 3: Implement** the functions in `journey_model.py`. Keep them free of Qt.
- [ ] **Step 4: Run** the file, all pass. Then run the full suite.
- [ ] **Step 5: Commit** `feat(journey): model for walk, week, records and history panels`

---

### Task 3: Bars widget and tab bar

**Files:**
- Create: `stepper_quests/bars_widget.py`
- Create: `stepper_quests/tab_bar.py`
- Test: `tests/test_bars_widget.py`

**Interfaces:**
- Produces:
  - `class BarsWidget(QWidget)` with `set_values(values: list[float], labels: list[str] | None = None, highlight_last: bool = True) -> None`; fixed height 72 px with labels, 56 px without; bars fill the width with 3 px gaps, zero values draw a 2 px baseline, the last bar is brass when `highlight_last`, others muted (`#5f5a50`), labels in muted 8 pt under each bar.
  - `class TabBar(QWidget)` with `__init__(names: list[str])`, `signal changed(str)`, `select(name: str) -> None`, `current() -> str`. Flat `QPushButton`s styled as text with a 2 px brass bottom border on the selected one, no frame.

- [ ] **Step 1: Write tests** in `tests/test_bars_widget.py`:

```python
def test_bars_render_to_pixmap(qapp):
    w = BarsWidget()
    w.set_values([0, 100, 50], ["M", "T", "W"])
    w.resize(300, 72)
    assert not w.grab().isNull()


def test_tab_bar_selection(qapp):
    bar = TabBar(["Journey", "Records"])
    seen = []
    bar.changed.connect(seen.append)
    bar.select("Records")
    assert bar.current() == "Records" and seen == ["Records"]
```

- [ ] **Step 2: Run**, fail with import errors.
- [ ] **Step 3: Implement** both widgets.
- [ ] **Step 4: Run**, pass.
- [ ] **Step 5: Commit** `feat(journey): bar strip and flat tab bar widgets`

---

### Task 4: Journey window rebuild

**Files:**
- Modify: `stepper_quests/journey_window.py` (rewrite the layout; keep `STYLE` colours, `_item`, `_rollup`, `_unlocked_text` where still useful)
- Test: `tests/test_journey_window.py` (new)

**Interfaces:**
- Consumes: Tasks 1 to 3; `ACHIEVEMENTS` from `progress.py`; `RouteWidget`.
- Produces: `JourneyWindow(store, quest, settings, parent=None)` with `refresh()`, `show_section(name: str)`, and read-only `current_tab() -> str` (for tests). Store setting key `"journey_tab"`.

Layout per spec section "Layout": hero (`breadcrumb`, `leg`, `sub`, `route`), a `QHBoxLayout` with the two panels, the `TabBar`, then a `QStackedWidget` whose pages are: Journey (the `QTreeWidget` inside a scroll-free page, the tree scrolls itself), Achievements (a `QScrollArea` with a two-column `QGridLayout` of panels), Records (three `QFormLayout`-style columns), History (`BarsWidget` + line + `QTableWidget` with 6 columns, read-only, no row numbers, stretch last section). Window `resize(900, 700)`.

Tree expansion: before `clear()`, collect `set` of `(volume.title, part.title, chapter.title)` keys for expanded items (store the key on each item with `setData(0, Qt.UserRole, key)`); after rebuilding, re-expand those. If the set is empty (first fill) expand the path to the active chapter and scroll the active waypoint to centre.

`show_section("achievements")` selects the Achievements tab; anything else selects Journey. `refresh()` leaves the tab untouched. Tab changes write `journey_tab`; the constructor reads it, default `"Journey"`.

- [ ] **Step 1: Write tests** in `tests/test_journey_window.py` (offscreen via the session `qapp`), with a `Settings(metres_per_step=0.7)` from `progress.py` and the mini quest fixture from `tests/fixtures/mini_quest.json`:

```python
def test_window_renders_empty_store(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    w.refresh()
    assert "No walks yet" in w.walk_panel_text()      # expose a tiny helper returning the panel's labels joined
    assert w.current_tab() == "Journey"


def test_show_section_selects_tab(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    w.show_section("achievements")
    assert w.current_tab() == "Achievements"
    w.show_section("route")
    assert w.current_tab() == "Journey"


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
```

- [ ] **Step 2: Run**, fail.
- [ ] **Step 3: Rewrite** `journey_window.py`.
- [ ] **Step 4: Run** the file and the full suite; all pass.
- [ ] **Step 5: Visual check**: `STEPPER_QUESTS_HOME=$(mktemp -d) .venv/bin/python -m stepper_quests --demo --demo-seed 3 --no-ble` is not usable while the real app runs (single instance), so instead write a tiny script in the scratchpad that builds `JourneyWindow` on a seeded temp store (reuse the `--demo-seed` seeding function from `app.py`, see `grep -n seed stepper_quests/app.py`) and `grab().save("out/journey-redesign-<tab>.png")` for each tab. Save the four PNGs under `out/`.
- [ ] **Step 6: Commit** `feat(journey): hero, live panels and tabs in the journey window`

---

### Task 5: Live refresh on session progress

**Files:**
- Modify: `stepper_quests/app.py` (`_handle`, add `_last_journey_refresh: float`)
- Test: `tests/test_app_wiring.py`

**Interfaces:**
- Consumes: `JourneyWindow.refresh()`.

In `_handle`, on `SessionProgress`, call `self._refresh_journey()` only if `time.time() - self._last_journey_refresh >= 1.0`; `_refresh_journey` records the time whenever it actually refreshes.

- [ ] **Step 1: Write test**

```python
def test_progress_refresh_is_throttled(app, monkeypatch):
    calls = []
    app._journey = type("W", (), {"isVisible": lambda s: True, "refresh": lambda s: calls.append(1)})()
    walk(app, 70, time.time(), 3.0)      # six cadence frames over three seconds (step 0.5)
    assert 2 <= len(calls) <= 4
```

Note: `walk` feeds synthetic timestamps while the throttle uses `time.time()`; make the throttle read a clock attribute `self._clock` defaulting to `time.time` and monkeypatch it in the test to follow the fed timestamps, so the assertion is exact (`len(calls) == 3`).

- [ ] **Step 2: Run**, fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** full suite, pass.
- [ ] **Step 5: Commit** `feat(app): refresh the journey window while walking, once a second`

---

### Task 6: README and screenshots

**Files:**
- Modify: `README.md` ("Tray app" section: one paragraph on the window layout and tabs)
- Deliver: `out/journey-redesign-*.png` from Task 4 (already written; confirm they exist)

- [ ] **Step 1: Edit README.**
- [ ] **Step 2: Commit** `docs: journey window layout`
