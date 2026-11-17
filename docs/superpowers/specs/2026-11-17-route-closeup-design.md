# Route close-up and denser waypoints

Owner request, 2026-11-17: "just more intermediate waypoints, a bit more
broken down graphics where i can see a guy walking the path and not the
whole rivendale journey and i see i am like 2% in".

## Intent

The road pays out too rarely to feel. Measured on the owner's data on
2026-11-17: 28 walks, 15,606 steps since 2026-10-29, 5 waypoints reached. A
typical walk is about 560 steps (0.24 walkable miles at 0.70 m per step).
Waypoints sit a median 2.5 walkable miles apart (about 5,750 steps, roughly
ten walks). The route strip draws the whole active part (Bag End to
Rivendell is 458 miles, `route_widget.py:36`), so one walk moves the marker
by about a pixel and the owner sees themselves "2% in".

The fix: something visibly changes on every walk, and a named story moment
arrives every few walks.

## Goals

- Each typical walk (about 560 steps) visibly moves a walking figure along
  the route, by several percent of the strip width.
- Each typical walk passes at least one road marker.
- No two consecutive story waypoints are more than 3 walkable miles apart
  (about 6,900 steps at the default stride).
- The whole-part view (Bag End to Rivendell, "you are here") stays
  available, but as a small secondary bar, not the main picture.

## Non-goals

- No change to counting, BLE, achievements, settings, or the tabs below the
  hero.
- No sprite images or animation libraries. Everything is QPainter, like the
  existing strip.
- No new settings.

## Anti-goals

- Invented story. New waypoints describe moments that are in the book (or
  are plain geography on Frodo's route, such as a named river, hill or
  road). No made-up events or dialogue.
- Toast spam. Road markers never raise their own toast.
- A dashboard look. The strip still reads like a road on a map.

## Approaches considered

1. **Auto road markers only.** A tick every quarter walkable mile.
   Cheap, and even everywhere, but no story.
2. **Hand-written story waypoints only**, until no gap exceeds 1 mile.
   About 1,000 new entries. Slow, and many would have to stretch the book.
3. **Both (chosen by the owner).** Auto markers give the per-walk reward.
   Story waypoints are added only where gaps are longest (over 3 walkable
   miles, 45 gaps today), which is where the book can carry them.

## Design

### 1. Story waypoints (data)

- Add waypoints to `stepper_quests/data/frodo.json` until no gap between
  consecutive waypoints exceeds 3.0 walkable miles. Today 45 gaps exceed
  that (10 exceed 5, all river legs, the longest 10.0, Field of Celebrant to
  North Undeep). Expect roughly 60 to 90 new entries.
- Same schema as existing entries: `id` (unique kebab-case), `name`,
  `road_miles`, `mode`, `story` (one or two sentences, past tense, same
  voice as today's entries). `mode` matches the leg it sits in.
- `road_miles` must keep the list sorted; placement inside a gap is by the
  book's description of that day where available, else even spacing.
- Where the book is thin (mostly the Anduin boat days), an entry may be
  plain landscape the chapter supports, for example the Brown Lands on the
  east bank or a night camp on an eyot, with no event invented. Every gap
  must still meet the 3.0 mile limit; the test has no exception list.
  (Builder's call, confirmed in review.)
- Sources for every new entry go in `stepper_quests/data/SOURCES.md`
  (chapter of the book, plus the Fonstad day table where it gives the place).
- Existing ids are never renamed or removed; reached-waypoint rows in the
  store reference them.
- New waypoints that lie behind the owner's current position are marked
  reached silently at startup by the existing `Progress.sync_silently`
  (`app.py:77`), so they do not toast.
- Tests: `test_frodo_data.py` gains a max-gap assertion (3.0 walkable miles)
  and a unique-id assertion; the `400 <= len <= 650` bound is widened to
  fit the new count.

### 2. Road markers (computed, not stored)

- A marker sits every 0.2 walkable miles along the whole road
  (about 460 steps at 0.70 m per step), at fixed positions
  `k * 0.2` walkable miles from Bag End. 0.2, not 0.25, so a typical
  560-step walk passes one. Every grid marker exists and counts as passed,
  even where it sits close to a story waypoint. Only its drawing yields:
  within 0.05 walkable miles of a story waypoint the tick is not drawn,
  because the waypoint dot stands for it.
- Markers are derived from walkable miles, not stored. "Passed" means
  `marker <= current walkable miles`.
- On the strip: small ticks across the road, brass when passed, muted ahead.
- End-of-walk toast ("Rest stop") gains a clause with the count of markers
  passed in that walk, for example
  `560 steps in 9 min. 1 road marker passed. Last sight of Hobbiton is 1,077 steps away.`
  With zero markers passed, the clause is omitted.
  Counted as markers between the walkable miles at walk start and at walk end.
- No other new toasts.

### 3. Route close-up (graphics)

The route panel in the journey window hero becomes two stacked widgets.

```
 BAG END ▮▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯ RIVENDELL      1.3%
 ───────────────────────────────────────────────────────────
  Crossing the                              Last sight
  East Road ━━━━╋━━━╋━━🚶┅┅╋┅┅┅╋┅┅┅╋┅┅┅┅┅ of Hobbiton
                         1,077 steps
```

**Overview bar** (new, about 28 px tall, full width):
- Thin track from the start of the stretch into the part's first waypoint
  (`journey_model.stretch_start`, the previous part's last waypoint, the
  same convention `RouteWidget.set_part` uses today) to the part's last
  waypoint. It agrees with `position.part_fraction`. Names of both
  ends in small caps at each end, chapter boundaries as faint ticks.
- Filled in brass up to the current position; a small brass notch at the
  position; percentage of the part walked at the right (`1.3%`).

**Close-up strip** (the existing `RouteWidget`, changed):
- Window start: the last reached story waypoint.
- Window end: the first story waypoint at or beyond
  `start + 4.0` walkable miles, or the part's last waypoint, whichever comes
  first. With the new data this usually shows 2 to 4 story waypoints.
- When a waypoint is reached, the window re-anchors on the next refresh
  (the "page turn" is the reward; no transition animation needed).
- The reached and next waypoints are always labelled. Other story
  waypoints in the window are labelled when the existing collision
  avoidance finds room, else they show as dots only. The next waypoint
  keeps its brass label, and under it the steps remaining, `1,077 steps`.
- Road markers drawn as ticks (section 2).
- The current dot marker is replaced by the walking figure.

**Walking figure:**
- A small hobbit silhouette, about 26 px tall, drawn with QPainter in brass
  with a dark outline: round head, short cloak body, two legs, a walking
  stick. Standing on the road at the current position.
- While a session is open, the legs and stick swing in a simple walk cycle
  (about 8 frames per second, driven by a `QTimer`). When no session is
  open, the figure stands still. The timer runs only while the window is
  visible and a session is open.
- The timer only advances the walk-cycle phase and calls the route
  widget's `update()`. It never calls the journey refresh or touches the
  store: data refresh stays throttled to once a second
  (`app.py:217`), and `_refresh_journey` also persists the running
  session (`app.py:283`). Tests cover window hide and show, session start,
  session end, and a discarded session (under 20 steps): the timer stops
  in each case where no session stays open.
- The figure walks on every leg mode, because the owner is walking. On
  boat legs it is drawn standing in a small boat outline, which still
  rocks in time with the walk cycle; on horse and carried legs it walks as
  on foot. (Design call, owner may override.)
- At a part boundary the close-up and overview use `position.part`, the
  next waypoint's part, as `journey_window.py:342` does today.
- The journey window learns whether a session is open from the app; the
  app already knows (it refreshes the window on `SessionProgress`,
  `app.py:215`).

## What stays the same

Hero breadcrumb, headline and projection line; the Walking now and Today
panels; all tabs; toast click navigation; the tray icon.

## Left to the builder

- Exact figure shapes, the overview bar's fonts and spacing, tick sizes.
- How the "session open" flag reaches the window (method or argument).
- Where marker maths lives (a small pure function in `quests.py` or
  `journey_model.py`), as long as it is unit tested without Qt.
- Writing and placing the new waypoint stories, within the anti-goals.
