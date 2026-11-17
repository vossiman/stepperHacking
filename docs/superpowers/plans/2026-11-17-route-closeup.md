# Route Close-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every walk visibly moves a walking hobbit along a zoomed-in road, passes a road marker, and a named story waypoint arrives every few walks.

**Architecture:** Pure maths (markers, close-up window, overview span) lives in `quests.py` and `journey_model.py` and is tested without Qt. `RouteWidget` is reworked into the close-up strip with an animated figure; a new `OverviewBar` widget sits above it. The app tells the journey window whether a session is open. Story waypoints are added to `frodo.json`.

**Tech Stack:** Python 3.10+, PySide6 (QPainter, QTimer), pytest with `QT_QPA_PLATFORM=offscreen` (`tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-11-17-route-closeup-design.md`

## Global Constraints

- Distances are walkable miles (`Waypoint.walkable_miles`), never road miles, in all new maths.
- Marker spacing `MARKER_SPACING = 0.2` walkable miles at `k * 0.2` from Bag End; drawing hidden within `MARKER_HIDE_RADIUS = 0.05` of a story waypoint; every grid marker still counts.
- Close-up window length `CLOSEUP_MILES = 4.0`.
- Max gap between consecutive story waypoints: 3.0 walkable miles.
- Walk cycle about 8 frames per second (`WALK_FRAME_MS = 125`); the timer only advances phase and calls `update()`.
- Palette unchanged: background `#1b1a17`, panel `#24221e`, brass `#d8b35a`, text `#e8e2d4`, muted `#8f8878`.
- No new settings, no new dependencies, no image assets.
- Existing waypoint ids are never renamed or removed.
- No em dashes in copy, comments, or commit messages.
- Run tests with `.venv/bin/pytest`. The worktree has no venv of its own: use the main checkout's, `/home/vossi/local_dev/stepperHacking/.venv/bin/pytest`, run from the worktree root.

## Review Focus

1. **End of the road** (`position.next is None`): close-up, overview and toast must render without division by zero; the figure stands at the last waypoint.
2. **Part boundary** (just past Rivendell, `position.reached` in Part 1, `position.part` is Part 2): overview starts at `stretch_start`, never clamps at 0% for 2.5 miles.
3. **Window hidden while walking, then opened**: figure must be animating on open; hidden window must not run the timer.
4. **Discarded session** (under 20 steps): animation stops, no marker clause in any toast.
5. **Stride change in Settings** moves position backwards: close-up re-anchors on the new reached waypoint without stale markers.

Each line has a test in the owning task below.

---

### Task 1: Road marker maths

**Files:**
- Modify: `stepper_quests/quests.py`
- Test: `tests/test_quests.py`

**Interfaces:**
- Produces:
  - `MARKER_SPACING: float = 0.2`, `MARKER_HIDE_RADIUS: float = 0.05`
  - `markers_between(start: float, end: float) -> list[float]`: grid markers `m` with `start < m <= end`, ascending.
  - `markers_passed(start: float, end: float) -> int`: `len(markers_between(start, end))`.
  - `Quest.drawn_markers(start: float, end: float) -> list[float]`: `markers_between(start, end)` minus any within `MARKER_HIDE_RADIUS` of a waypoint's `walkable_miles`.

- [ ] **Step 1: Write the failing tests**

```python
from stepper_quests.quests import markers_between, markers_passed

def test_markers_between_is_half_open_grid():
    assert markers_between(0.0, 0.6) == pytest.approx([0.2, 0.4, 0.6])
    assert markers_between(0.2, 0.39) == []

def test_markers_passed_typical_walk_passes_one():
    # 560 steps at 0.7 m = 0.2436 walkable miles
    assert markers_passed(0.9, 0.9 + 0.2436) == 1

def test_marker_near_waypoint_counts_but_is_not_drawn(quest):
    # mini quest: Hobbiton at 10.0 walkable miles
    assert 10.0 == pytest.approx(markers_between(9.9, 10.1)[0])
    assert quest.drawn_markers(9.9, 10.1) == []
    assert quest.drawn_markers(9.5, 9.7) == pytest.approx([9.6])
```

Floating point: compute markers as `k * MARKER_SPACING` for integer `k` from `floor(start / s + 1e-9) + 1`, and compare with a `1e-9` tolerance so `0.6` is included.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_quests.py -v`. Expected: FAIL, import error.
- [ ] **Step 3: Implement** the three functions in `quests.py`.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_quests.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(quests): road marker grid every 0.2 walkable miles`

### Task 2: Close-up window and overview span

**Files:**
- Modify: `stepper_quests/journey_model.py`
- Test: `tests/test_journey_model.py`

**Interfaces:**
- Consumes: `stretch_start(quest, waypoint)` (exists, `journey_model.py:21`).
- Produces:
  - `CLOSEUP_MILES: float = 4.0`
  - `@dataclass(frozen=True) class Span: start: float; end: float; waypoints: list[Waypoint]` (waypoints with `start <= walkable_miles <= end`).
  - `closeup_span(quest: Quest, position: Position) -> Span`
  - `overview_span(quest: Quest, part: Part) -> Span` (waypoints = the part's chapter-ending waypoints, used for chapter ticks).
  - `part_label_ends(quest: Quest, part: Part) -> tuple[str, str]`: names of the waypoint at `stretch_start` (the previous part's last, or the part's first at Bag End) and the part's last waypoint.

Rules for `closeup_span`:
- `start = position.reached.walkable_miles`.
- `end` = `walkable_miles` of the first waypoint with `walkable_miles >= start + CLOSEUP_MILES`, capped at the last waypoint of `position.part`; never below `position.next.walkable_miles`.
- End of road (`position.next is None`): `start = stretch_start(quest, reached)`, `end = reached.walkable_miles`.

- [ ] **Step 1: Write the failing tests** (mini quest walkable miles: Bag End 0, Hobbiton 10, Bucklebury 20, Far Bank 30, Bree 50)

```python
def test_closeup_starts_at_reached_and_reaches_next(quest):
    s = jm.closeup_span(quest, quest.position(5.0))
    assert (s.start, s.end) == (0.0, 10.0)
    assert [w.name for w in s.waypoints] == ["Bag End", "Hobbiton"]

def test_closeup_reanchors_after_waypoint(quest):
    s = jm.closeup_span(quest, quest.position(10.5))
    assert (s.start, s.end) == (10.0, 20.0)

def test_closeup_after_stride_change_moves_back(quest):
    assert jm.closeup_span(quest, quest.position(9.0)).start == 0.0

def test_closeup_at_end_of_road_has_length(quest):
    s = jm.closeup_span(quest, quest.position(1000.0))
    assert s.end > s.start

def test_overview_span_starts_at_stretch_start(quest):
    part = quest.volumes[0].parts[0]
    s = jm.overview_span(quest, part)
    assert (s.start, s.end) == (0.0, 50.0)
```

Add a test against the real data for the part boundary (Review Focus 2): load `Quest.default_path()`, take `pos = quest.position(rivendell.walkable_miles + 0.5)`, assert `overview_span(quest, pos.part).start == rivendell.walkable_miles` and `pos.part_fraction > 0`.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_journey_model.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** in `journey_model.py`.
- [ ] **Step 4: Run** again. Expected: PASS.
- [ ] **Step 5: Commit** `feat(journey): close-up and overview spans`

### Task 3: Marker clause in the Rest stop toast

**Files:**
- Modify: `stepper_quests/copy.py:22-31`, `stepper_quests/app.py:271-272`
- Test: `tests/test_app_copy.py`, `tests/test_app_wiring.py`

**Interfaces:**
- Consumes: `markers_passed(start, end)` from Task 1.
- Produces: `end_message(session, position, metres_per_step, markers: int = 0) -> str`.

Copy, exact: after the walked sentence insert `1 road marker passed.` or `N road markers passed.`; omit when `markers == 0`.

- [ ] **Step 1: Write the failing tests**

```python
def test_end_message_counts_markers(quest):
    session = Session(start=1000.0, end=1000.0 + 9 * 60, steps=560.0)
    msg = end_message(session, quest.position(5.0), MPS, markers=1)
    assert msg == "560 steps in 9 min. 1 road marker passed. Hobbiton is 11,495 steps away."

def test_end_message_plural_and_zero(quest):
    session = Session(start=1000.0, end=1600.0, steps=1200.0)
    assert "3 road markers passed." in end_message(session, quest.position(5.0), MPS, markers=3)
    assert "marker" not in end_message(session, quest.position(5.0), MPS, markers=0)
```

In `test_app_wiring.py`, add `test_rest_stop_toast_counts_markers`: monkeypatch `app._toast` to record calls, walk 60 spm for long enough to exceed 0.2 walkable miles, end the session via `app.tracker.tick`, assert the "Rest stop" body contains `road marker`. Add `test_discarded_session_has_no_rest_stop_toast` asserting no "Rest stop" call for a session under 20 steps (Review Focus 4).

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_app_copy.py tests/test_app_wiring.py -v`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.** In `App._session_ended`, the session is already upserted, so `end = steps_to_miles(store.lifetime_steps(), mps)` and `start = end - steps_to_miles(session.steps, mps)`; pass `markers_passed(start, end)`.
- [ ] **Step 4: Run** again. Expected: PASS, and the full suite still passes.
- [ ] **Step 5: Commit** `feat(toast): count road markers passed in the Rest stop toast`

### Task 4: Close-up strip with walking figure

**Files:**
- Modify: `stepper_quests/route_widget.py` (rework)
- Test: `tests/test_route_widget.py` (new)

**Interfaces:**
- Consumes: `Span` (Task 2), `Quest.drawn_markers` (Task 1).
- Produces on `RouteWidget`:
  - `set_span(span: Span, position: Position, now: float, markers: list[float], steps_to_next: str | None) -> None` (replaces `set_part`; `steps_to_next` is pre-formatted, for example `"1,077 steps"`, `None` at end of road).
  - `set_walking(walking: bool) -> None`: starts or stops the animation timer; the timer only runs while `walking and self.isVisible()`.
  - `is_animating() -> bool`: whether the timer is active.
  - `labelled_names() -> list[str]`: names of labels drawn in the last paint, for tests.
  - Overrides `showEvent` and `hideEvent` to start/stop the timer per the rule above.

Drawing rules:
- Same curved road as today, mapped over `span.start..span.end`. Brass solid behind `now`, dashed muted ahead.
- Story waypoint dots as today. Marker ticks: short strokes across the road, 6 px, brass when `<= now`, muted ahead.
- Labels: reached and next always; others when collision avoidance finds room (existing loop, `route_widget.py:132-144`). Under the next label, `steps_to_next` in muted text.
- Figure: about 26 px tall, feet on the road point at `now`. Head circle, cloak (rounded trapezoid), two legs, a stick. Brass fill, `#1b1a17` outline 1.5 px. Leg and stick angle `±18° * sin(phase)`; `phase` advances by `2π/8` per timer tick; standing pose at `phase = 0`.
- Boat legs (`position.next.mode == "boat"`): draw a small boat hull under the figure, rocking by `±4° * sin(phase)`, legs hidden.

- [ ] **Step 1: Write the failing tests**

```python
def test_paints_and_labels_reached_and_next(quest, qapp):
    w = RouteWidget(); w.resize(800, 200)
    pos = quest.position(5.0)
    w.set_span(jm.closeup_span(quest, pos), pos, 5.0, quest.drawn_markers(0.0, 10.0), "11,495 steps")
    w.grab()  # forces paintEvent offscreen
    assert {"Bag End", "Hobbiton"} <= set(w.labelled_names())

def test_end_of_road_paints(quest, qapp):
    w = RouteWidget(); w.resize(800, 200)
    pos = quest.position(1000.0)
    w.set_span(jm.closeup_span(quest, pos), pos, 1000.0, [], None)
    w.grab()

def test_timer_runs_only_when_walking_and_visible(qapp):
    w = RouteWidget()
    w.set_walking(True)
    assert not w.is_animating()
    w.show(); assert w.is_animating()
    w.hide(); assert not w.is_animating()
    w.show(); w.set_walking(False); assert not w.is_animating()
```

Also `test_timer_tick_does_not_call_parent_refresh`: put the widget inside a stub parent whose `refresh` raises; fire the timer's `timeout` signal directly; assert nothing raised.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_route_widget.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the widget.
- [ ] **Step 4: Run** again. Expected: PASS. (`journey_window.py` still calls `set_part`; it is switched in Task 6, so leave `set_part` in place until then or update the call in this task with a `closeup_span` call; either is fine as long as the full suite passes at the commit.)
- [ ] **Step 5: Commit** `feat(route): close-up strip with road markers and a walking hobbit`

### Task 5: Overview bar

**Files:**
- Create: `stepper_quests/overview_widget.py`
- Test: `tests/test_overview_widget.py`

**Interfaces:**
- Consumes: `overview_span`, `part_label_ends` (Task 2).
- Produces: `class OverviewBar(QWidget)` with `set_overview(span: Span, ends: tuple[str, str], now: float, fraction: float) -> None` and `percent_text() -> str`.

Rules: fixed height 28 px; thin track; brass fill to `now`; brass notch at `now`; chapter-end ticks at `span.waypoints` positions; end names upper-cased in a smaller font at each end; percent at the right, one decimal (`1.3%`), from `fraction` (pass `position.part_fraction`).

- [ ] **Step 1: Write the failing tests**

```python
def test_percent_one_decimal(qapp):
    bar = OverviewBar()
    bar.set_overview(jm.Span(0.0, 458.0, []), ("Bag End", "Rivendell"), 6.0, 6.0 / 458.0)
    assert bar.percent_text() == "1.3%"
    bar.resize(800, 28); bar.grab()

def test_full_part_is_100(qapp):
    bar = OverviewBar()
    bar.set_overview(jm.Span(0.0, 10.0, []), ("A", "B"), 10.0, 1.0)
    assert bar.percent_text() == "100.0%"
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_overview_widget.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** again. Expected: PASS.
- [ ] **Step 5: Commit** `feat(route): overview bar of the whole part`

### Task 6: Wire the journey window and the app

**Files:**
- Modify: `stepper_quests/journey_window.py:168-174, 341-343`, `stepper_quests/app.py` (session start, end, `open_journey`)
- Modify: `README.md` (journey window paragraph)
- Test: `tests/test_journey_window.py`, `tests/test_app_wiring.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 4, 5.
- Produces: `JourneyWindow.set_walking(walking: bool) -> None` (forwards to `self.route.set_walking`); attribute `JourneyWindow.overview: OverviewBar`.

Changes:
- Route panel holds `OverviewBar` above `RouteWidget`.
- `refresh()` replaces the `set_part` call with `closeup_span`, `drawn_markers(span.start, span.end)`, `steps_to_next` (`f"{format_steps(steps)} steps"`, `None` at end of road) and `overview.set_overview(overview_span(quest, position.part), part_label_ends(...), miles, position.part_fraction)`.
- App: call `self._journey.set_walking(True)` in `_session_started`, `set_walking(False)` in `_session_ended` (both discarded and kept) and in `quit`, and in `open_journey` pass `self.tracker.current is not None` after creating the window.
- README: one or two sentences describing the close-up, the walking figure, road markers every 0.2 walkable miles, and the overview bar.

- [ ] **Step 1: Write the failing tests**

```python
# test_journey_window.py
def test_route_shows_closeup_and_overview(store, quest, settings):
    w = JourneyWindow(store, quest, settings)
    assert w.overview.percent_text().endswith("%")

# test_app_wiring.py
def test_journey_animates_while_walking(app):
    app.open_journey(None)
    start = t0()
    app.on_cadence(60, start)
    assert app._journey.route.is_animating()

def test_opening_journey_mid_walk_animates(app):
    app.on_cadence(60, t0())
    app.open_journey(None)
    assert app._journey.route.is_animating()

def test_animation_stops_on_discarded_session(app):
    app.open_journey(None)
    start = t0()
    app.on_cadence(60, start)
    app._handle(app.tracker.tick(start + 600))
    assert not app._journey.route.is_animating()
```

Add `test_animation_stops_on_session_end` for a kept session (walk 60 spm for 120 s, then tick past idle). Assert that `_last_journey_refresh` throttling is unchanged by reusing `test_progress_refresh_is_throttled` (it must still pass).

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_journey_window.py tests/test_app_wiring.py -v`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.** Remove `RouteWidget.set_part` if nothing else calls it.
- [ ] **Step 4: Run** `.venv/bin/pytest -q`. Expected: all PASS.
- [ ] **Step 5: Visual check.** Run `python -m stepper_quests --demo` (temp home, no BLE; see `stepper_quests/__main__.py:9`), take a screenshot, and confirm: figure visible on the road, markers visible, overview shows a percentage, labels readable at 900 px width.
- [ ] **Step 6: Commit** `feat(journey): close-up route, overview bar, animate while walking`

### Task 7: Story waypoints for long gaps

**Files:**
- Modify: `stepper_quests/data/frodo.json`, `stepper_quests/data/SOURCES.md`
- Test: `tests/test_frodo_data.py`

**Interfaces:**
- Consumes: nothing new. Ids stay unique kebab-case; schema unchanged.

List the gaps to fill with:

```bash
.venv/bin/python -c "
from stepper_quests.quests import Quest, load_quest
q = load_quest(Quest.default_path()); ws = q.waypoints
for a, b in zip(ws, ws[1:]):
    g = b.walkable_miles - a.walkable_miles
    if g > 3.0: print(f'{g:5.2f}  {a.name} -> {b.name}  [{b.mode}, {b.chapter.title}]')
"
```

Expected today: 45 lines.

Rules for each new entry:
- `road_miles` between its neighbours, placed from the book's account of that day where available, else evenly. Enough entries per gap that every resulting gap is at most 3.0 walkable miles (remember boat legs are ratio 4, horse 3: a 40 road-mile boat gap is 10 walkable miles and needs at least 3 new entries).
- `mode` equals the mode of the waypoint that ends the gap.
- `story`: one or two sentences, past tense, same voice as neighbours. Only events or places in the book; where the book is thin (Anduin days) plain landscape the chapter supports. No invented events or dialogue.
- `SOURCES.md`: add a section "Waypoints added 2026-11-17" listing each new id with its book chapter.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_gap_over_three_walkable_miles(quest):
    gaps = [(b.walkable_miles - a.walkable_miles, b.id)
            for a, b in zip(quest.waypoints, quest.waypoints[1:])]
    assert max(gaps)[0] <= 3.0, max(gaps)

def test_ids_unique(quest):
    ids = [w.id for w in quest.waypoints]
    assert len(ids) == len(set(ids))
```

Widen the bound in `test_loads` to `400 <= len(quest.waypoints) <= 800`. Existing anchor tests (`rivendell` 458, `caras-galadhon` 920, `parth-galen` 1309) must still pass.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_frodo_data.py -v`. Expected: max-gap test FAIL.
- [ ] **Step 3: Add the entries**, part by part; rerun the gap script after each part.
- [ ] **Step 4: Run** `.venv/bin/pytest -q`. Expected: all PASS; gap script prints nothing.
- [ ] **Step 5: Commit** `feat(data): story waypoints so no gap exceeds 3 walkable miles`
