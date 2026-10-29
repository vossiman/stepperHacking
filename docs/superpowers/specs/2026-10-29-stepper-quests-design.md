# Stepper Quests: tray app design

Date: 2026-10-29. Status: draft for approval.

## Intent

Turn the existing `stepper.py` BLE step counter (Sportstech DFX100, see
README) into a background tray app for the Cinnamon desktop that counts every
step automatically, keeps a lifetime total, and turns the total into progress
along Frodo's road through Middle-earth. The point is motivation: a small
story reward every few days, not a fitness dashboard.

## Goals

- Zero-touch counting: the app autostarts at login, stays connected to the
  stepper (or reconnects when the console sleeps), and a session starts at the
  first nonzero cadence frame and ends after a quiet period. No clicks.
- A tray icon that shows idle / stepping / reconnecting at a glance, with
  notification bubbles on session start and end.
- A journey window (opened from the tray menu) with the route of the active
  part, the current position, and stats.
- Quests in reading order: volume, part, chapter, waypoint. Waypoints every
  2 to 4 road miles so something completes every few days at the owner's pace.
- Story-tied achievements for streaks and totals.
- Tiny footprint: one Python process, a few MB, near-zero CPU.

## Non-goals

- No phone app, no cloud, no accounts, no sharing.
- No exact step count. The console only reports cadence; steps are integrated
  (README explains). Good enough for a journey.
- No scanned Tolkien maps. The route is our own stylized line with named
  waypoints (copyright).
- No resistance or heart-rate data; the console does not expose any.

## Anti-goals (would make it a failure even if it works)

- Missing steps because the app was not running or was not connected: the
  reconnect loop must be robust, and a session must never be lost to a crash
  (persist frequently).
- Eating resources or nagging. No polling UI, no popups beyond start/stop
  bubbles and achievement bubbles.
- An achievement drought: weeks with nothing completed.

## Constraints

- Platform: Linux Mint / Cinnamon on the owner's desktop, adapter `hci0`. Stepper
  MAC `AA:BB:CC:DD:EE:FF`, plugged into mains (battery drain is not a concern).
- Language: Python 3, reusing the protocol code in `stepper.py` (bleak).
- Tray: Qt StatusNotifierItem via PySide6, the same stack as the owner's
  stream-mode and handsfree apps. Set `setApplicationName` and
  `setDesktopFileName` explicitly and add a single-instance guard (lessons from
  those apps, see homelab-wiki `stream-mode` page). Autostart via
  `~/.config/autostart/stepper-quests.desktop`; the launcher must `cd` into the
  app directory and detach (`setsid`), again per the wiki.
- Tray icon must not be a plain colored disc: handsfree already uses a green
  circle, stream-mode a disc with an "S". Use footprints.
- The phone app must not be connected at the same time (it is not paired any
  more; just document it).

## Behaviour

### Connection and sessions

- Poll-driven protocol as in README: init sequence, then `F0 A2 01 01 94`
  every 0.5 s; cadence is byte 9 of the B2 reply.
- State machine: `disconnected` -> (scan/connect by MAC, retry with backoff
  capped at 15 s) -> `connected-idle` -> (first cadence > 0) -> `stepping` ->
  (cadence == 0 for `idle_timeout`, default 60 s) -> `connected-idle`.
  Link drop from any state -> `disconnected`. The console is expected to go
  to sleep and drop the link after a while; that is normal, not an error.
- A session survives link drops: it ends only after `idle_timeout` of
  wall-clock time without a nonzero cadence frame, counting time spent
  disconnected. `dt` is measured from the previous frame but capped at 2 s,
  so a gap after a reconnect contributes nothing.
- Reconnect is by MAC (no name scan) with backoff. Whether the console still
  advertises while asleep is unknown; the builder checks on the hardware. If
  it does not, the loop just keeps retrying the connect at the capped
  interval, and the first few seconds of a session are lost. Accepted.
- Steps per frame: `spm * dt / 60`, dt measured between frames, same as
  `stepper.py`. The idle timeout seconds contribute zero steps.
- A session record: start, end, steps (float, displayed rounded), max and
  mean spm, duration of nonzero cadence. Sessions shorter than 20 steps are
  discarded (bumping the pedal).

### Persistence

- SQLite file at `~/.local/share/stepper-quests/steps.db`: `sessions`,
  `achievements` (name, unlocked_at), `settings`. Lifetime total is the sum
  of sessions, never a separately stored counter.
- During a session, write the running session row every 10 s so a crash
  loses at most 10 s.
- Keep writing the per-session CSVs in `data/` that `stepper.py` writes today
  (raw frames are useful for protocol re-checks). Builder's call whether that
  lives behind a setting.

### Tray

- Icons (SVG, rendered at panel size): footprints outline grey = connected
  idle; footprints filled brass with one foot blinking = stepping; footprints
  dashed outline = disconnected / reconnecting. Tooltip shows state, today's
  steps and current spm.
- Bubbles: session start ("Leaving Crickhollow. 3,140 steps to Bree."),
  session end ("1,812 steps in 31 min. Bree is 1,328 steps away."), waypoint
  reached (name plus its story line), achievement unlocked. Nothing else.
- Bubbles are the app's own toast: a small frameless always-on-top Qt widget
  in the bottom-right corner of the primary screen, Telegram style, that
  slides in, stays about 5 s (achievements and waypoints 8 s) and fades.
  Clicking it opens the journey window on the matching section (achievements
  list for an achievement, the route for a waypoint or session). Own widget
  rather than freedesktop notifications because click-to-open actions and
  placement are unreliable through Cinnamon's notification daemon; that is
  my call, the builder may use desktop notifications if actions work there.
- The journey window gets an Achievements section: unlocked badges with date,
  locked ones greyed with their condition.
- Menu: Open journey window; today's and lifetime steps (disabled rows);
  Quests...; Settings...; Quit.

### Journey window

Layout as in the approved mockup (artifact "Stepper Quests",
https://claude.ai/artifact/Hw9P1tGzAyXxLLpLqX77u9): breadcrumb (volume,
part, chapter), current leg name, stylized route line of the active part with
waypoints and the owner's marker, then tiles: steps to next waypoint, chapter
progress, part progress, today, lifetime (plus km and road miles), best day.
Below, the quest list in reading order with done / active / ahead dots, each
chapter showing miles, steps and estimated days at the current pace, and the
active chapter expanded to its waypoints. Settings for metres per step and
minutes per day live in the Settings dialog, not in the window.

### Quests

- Hierarchy: volume -> part -> chapter -> waypoint. Volumes use the familiar
  three titles; parts are Tolkien's inner books, named "Part 1 / Part 2".
  Frodo's road runs Fellowship Part 1 and 2, Two Towers Part 2, Return of the
  King Part 2. The Aragorn parts are out of scope now but the data format must
  allow adding them as separate quests later.
- Quest data is a YAML/JSON file shipped with the app, no code. Each waypoint:
  name, cumulative road miles from Bag End, travel mode, one or two sentences
  of what happens there (own words, no quotations longer than a short phrase).
  Each chapter: Tolkien's chapter title and the leg it covers.
- Mileage source: the Eowyn Challenge tables (eowynchallenge.net, mirrored on
  fan sites). The builder pulls the full waypoint table for Bag End to Mount
  Doom from a mirror and uses its cumulative miles; the figures in the mockup
  (458 to Rivendell, 462 to Lórien, 389 to Rauros, 470 to Mount Doom) are the
  stage totals to check against.
- Waypoint density on foot legs: every 2 to 4 road miles. Where the Eowyn
  table is coarser, add named places from the books and maps in between. On
  boat and horse legs only the places the books name are waypoints (the
  Anduin has about eight); gaps up to roughly 10 walkable miles (two weeks)
  are accepted there. No invented places.
- Travel-mode ratios convert road miles to walkable miles: foot 1:1, pony or
  horse 1:3, boat 1:4, carried 1:1, eagle free (epilogue, not a leg). Ratios
  live in the quest file so they can be tuned without code.
- Rule for tagging a leg: it counts as foot whenever the company walked,
  even if Frodo himself rode. So Weathertop to the Ford (Frodo on Bill the
  pony, everyone else on foot) is foot; the final Asfaloth gallop to the
  Ford (Frodo alone on the horse) is horse; the Anduin is boat. Owner's
  decision, 2026-10-29.
- Steps to walkable miles: `steps * metres_per_step / 1609.344`, default 0.7 m,
  a setting.
- Progress is derived from lifetime steps each time it is displayed; nothing
  about position is stored. Changing metres per step therefore moves the
  marker, which is acceptable and should be noted in the setting's help text.
- Only one quest (Frodo's road) exists now. Completed waypoints beyond the end
  of the data show an "end of the road" state, not an error.

### Achievements

Story-tied, each unlocked once, recorded in the db, announced by a bubble.
Initial set (names open to change):

- Second Breakfast: two sessions in one calendar day, starts at least two
  hours apart.
- Elevenses: a session started before 11:00.
- Hobbit's Pace: 7 days in a row with at least one session.
- Rangers of the North: 30 days in a row.
- Long-expected Party: lifetime 100,000 steps.
- Sting Glows: a new best day (repeatable; the bubble says the new record).
- Not all those who wander: longest single session so far (repeatable).
- The Road Goes Ever On: a part completed (repeatable per part).

Streak days are calendar days in local time; a day counts with one session of
at least 20 steps.

## Pace reference (for sizing waypoints and checking the drought rule)

At 30 min a day, 58 spm, 0.7 m per step: about 1,740 steps and 0.75 road
miles a day. Waypoints at 2 to 4 miles mean one every 3 to 5 days. The whole
walkable road (about 1,480 miles after ratios) is roughly five years; that is
accepted.

## Left to the builder

- Package layout, config file format, exact Qt widgets, how the route line is
  drawn (QPainter or embedded QtWebEngine is the builder's call; prefer the
  lighter one).
- Which fan mirror of the Eowyn table to use and how to transcribe it; keep a
  `SOURCES.md` next to the quest file.
- Test strategy: the protocol parser and the integration from cadence to steps
  are pure functions and get unit tests with the recorded frames in `data/`;
  the state machine gets tests with a fake notifier; the UI is checked by hand.
- Git: this folder is not a repository yet. Initialize one before building
  and commit this document first.
