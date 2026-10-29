# Journey window redesign

Owner approved the mockup (claude.ai artifact WvdS4kmuC3W3iUuj3dcnZp, version 4)
on 2026-10-29. This document is the written form of that mockup plus the
rules it does not show.

## Intent

The current journey window shows everything at once: three headline lines,
the route strip, six tiles, a 460 px quest tree and the full achievement
list. Opening it should instead answer "how am I doing" in one screen:
what is happening now (or what happened last), today, the last days and the
week. The story position stays as the headline. Everything else moves into
tabs.

## Goals

- One screen on open, no scrolling needed at 900 x 700.
- Current session visible live while stepping; last session otherwise.
- Today, last 7 days and this-week-vs-last-week visible without a click.
- The long-horizon projection ("years to Mount Doom") is a single muted
  line in the hero, never a tile.
- Details reachable in one click: the quest tree, achievements, records and
  totals, a day-by-day history.
- Toast clicks still land on the right place.

## Non-goals

- No change to counting, persistence, toasts, tray or achievements logic.
- No new settings.
- No charts library; bars are plain Qt painting.

## Anti-goal

A redesign that hides the story. The hero line must still read like a place
in the book, not like a fitness dashboard.

## Layout (top to bottom)

1. **Hero**
   - Breadcrumb: `VOLUME  ·  PART  ·  CHAPTER` (as today).
   - Headline (serif, large): `<chapter leg>, <N> steps to <next waypoint>`.
     At the end of the road: `<chapter leg>. The road ends here.`
   - Subline (muted): road miles left to the Crack of Doom and the
     projection at the 30-day pace, in the existing `pace_steps_per_day`
     sense. Format: `1,779 road miles to the Crack of Doom. About 4 years
     at your pace.` Units: `N days` under 60 days, `N months` under 24
     months, else `N years M months` (drop ` M months` when M is 0).
     When there is no walk yet: `1,779 road miles to the Crack of Doom.
     Your first walk sets the pace.`
   - Route strip (existing `RouteWidget`, unchanged).

2. **Two panels side by side**
   - Left, **Walking now** while a session is open, else **Last walk**.
     Title row carries a pill with the start time (`today 14:33`,
     `yesterday 09:10`, else `Mon 27 Oct`). Big number: steps. Below, three
     label/value lines: `Length` (`5 min`), `Pace` (`66 spm mean, 74 peak`),
     `Reached` (names of waypoints reached during that session, comma
     joined, or `nothing new, 1,965 to go`). With no sessions at all the
     panel says `No walks yet` and `Start stepping and this fills in.`
   - Right, **Today**. Pill with the walk count (`1 walk`, `3 walks`,
     `no walks yet`). Big number: today's steps. Below, a 7-day bar strip
     ending today (today's bar in brass, others muted, weekday initials
     under each bar, zero days drawn as a 2 px baseline). Under the bars one
     line: `This week 2,140 steps · last week 3,800 · best day 1,520 (Sat)`
     where "week" is Monday to Sunday and best day is within the last 7
     days. Omit the best-day clause when the last 7 days are all zero.

3. **Tabs**, in this order, Journey selected on open: Journey,
   Achievements, Records, History. The selected tab is remembered in the
   store setting `journey_tab` across opens.
   - **Journey**: the existing tree, same content and marks. On refresh,
     keep the user's expansion state (collect expanded item keys before
     `clear()`, restore after). First open expands the path to the active
     chapter and scrolls the active waypoint to centre, as today.
   - **Achievements**: a two-column grid of panels. Unlocked first (title,
     body, unlock date and note), then locked at reduced opacity (title and
     condition). For the streak achievements append progress: `1 of 7` or
     `12 of 30`.
   - **Records**: three columns of label/value pairs.
     - Records: Best day, Longest walk, Fastest walk (highest mean spm),
       Peak cadence (highest max spm), Longest streak, Best week (Monday to
       Sunday total), Earliest start (time of day).
     - Totals: Steps, Distance (`0.23 km, 0.15 road miles`), Walks, Time
       walking, Walking days (`14 of 30 since start`), Waypoints reached
       (`1 of 618`), Chapters done (`0 of 62`).
     - Pace: Per walking day, Per week 4-wk avg, Next waypoint
       (`1,965 steps, about 6 walks` using the mean steps per walk),
       End of chapter, Rivendell, Mount Doom (each a duration at the
       30-day pace, same unit rules as the hero), Frodo's pace
       (`you are at 0.3% of his 6 months`, meaning road miles walked over
       total road miles, as a percentage).
     - With no sessions every value reads `none yet` or `0`.
   - **History**: a 30-day bar strip (same drawing as the 7-day one, no
     weekday labels, today in brass) with the line `Last 30 days. Walking
     days 14 of 30.`, then a table of the last 30 days, newest first, with
     columns Day, Steps, Walks, Minutes, Mean spm, Reached. Days without a
     walk show `0` and empty cells in muted colour. Only days since the
     first session are listed, so a fresh install shows one row.

## Live updates

While a session is open the app already refreshes the window on toasts and
on session end. Add a refresh on each `SessionProgress` event, but at most
once per second, so the "Walking now" numbers move while stepping. The
window must not lose the selected tab, the tree expansion or the scroll
position on refresh.

## Navigation from toasts

`show_section(name)` keeps its signature. `route` selects the Journey tab
and centres the active waypoint; `achievements` selects the Achievements tab. Any
other name selects Journey.

## Visual rules

Existing palette (background `#1b1a17`, panel `#24221e`, brass `#d8b35a`,
text `#e8e2d4`, muted `#8f8878`) and fonts stay. The tab bar is a flat row
of text buttons with a 2 px brass underline on the selected one, no Qt
default tab frame. The window opens at 900 x 700 and the content area
scrolls vertically only inside the tab body, never the hero.

## Owner rulings

- Tab order Journey, Achievements, Records, History (ruled 2026-10-29 after
  trying Stats and Achievements first).
- "Records" replaces "Stats" as the tab name; the lifetime totals live
  there, not in the hero.

## Left to the builder

- Exact bar drawing (a small `QWidget` subclass painting rectangles).
- How expansion state is keyed (chapter and part titles are unique per
  volume; key by `(volume, part, chapter)` tuple).
- Whether the day table is a `QTableWidget` or a `QTreeWidget` with the
  header shown.
