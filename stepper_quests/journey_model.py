"""Numbers behind the journey window, kept free of Qt so they can be unit tested."""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .copy import format_steps
from .quests import Chapter, Position, Quest, Waypoint, miles_to_steps
from .store import Store

DEFAULT_PACE = 1740
PACE_DAYS = 30


def pace_steps_per_day(store: Store, today: date) -> float:
    active = [s for s in store.recent_daily_steps(PACE_DAYS, today) if s > 0]
    return sum(active) / len(active) if active else DEFAULT_PACE


def stretch_start(quest: Quest, waypoint: Waypoint) -> float:
    """Walkable miles where the stretch ending at ``waypoint`` begins."""
    index = quest.waypoints.index(waypoint)
    return quest.waypoints[index - 1].walkable_miles if index else 0.0


def chapter_miles(quest: Quest, chapter: Chapter) -> float:
    return chapter.waypoints[-1].walkable_miles - stretch_start(quest, chapter.waypoints[0])


@dataclass(frozen=True)
class ChapterEstimate:
    miles: float
    steps: float
    days: float


def chapter_estimate(quest: Quest, chapter: Chapter, metres_per_step: float,
                     pace: float) -> ChapterEstimate:
    miles = chapter_miles(quest, chapter)
    steps = miles_to_steps(miles, metres_per_step)
    return ChapterEstimate(miles, steps, steps / pace)


def chapter_label(est: ChapterEstimate) -> str:
    miles = f"{est.miles:.0f}" if est.miles >= 10 else f"{est.miles:.1f}"
    days = max(1, round(est.days))
    return f"{miles} mi, {format_steps(est.steps)} steps, ~{days} day{'' if days == 1 else 's'}"


def _miles(position: Position) -> float:
    if position.next is None:
        return position.reached.walkable_miles
    return position.next.walkable_miles - position.miles_to_next


def waypoint_state(waypoint: Waypoint, position: Position) -> str:
    if waypoint.walkable_miles <= _miles(position):
        return "done"
    if waypoint is position.next:
        return "active"
    return "ahead"


def chapter_state(chapter: Chapter, position: Position) -> str:
    if chapter.waypoints[-1].walkable_miles <= _miles(position):
        return "done"
    if chapter is position.chapter:
        return "active"
    return "ahead"


def road_miles_walked(position: Position) -> float:
    reached, nxt = position.reached, position.next
    if nxt is None:
        return reached.road_miles
    return reached.road_miles + position.fraction_to_next * (nxt.road_miles - reached.road_miles)


@dataclass(frozen=True)
class DayStats:
    steps: float
    sessions: int
    minutes: float
    mean_spm: float


def today_stats(store: Store, day: date) -> DayStats:
    rows = store.sessions_on_day(day)
    steps = sum(r["steps"] for r in rows)
    minutes = sum(r["active_seconds"] for r in rows) / 60
    return DayStats(steps, len(rows), minutes, steps / minutes if minutes else 0)


def achievement_status(achievements, unlocked) -> dict[str, tuple[float, str] | None]:
    """Latest (at, note) per achievement name; repeatables match ``name:`` keys."""
    status: dict[str, tuple[float, str] | None] = {a.name: None for a in achievements}
    repeatable = {a.name for a in achievements if a.repeatable}
    for key, at, note in unlocked:
        name = key.split(":", 1)[0] if ":" in key else key
        if name not in status or (name in repeatable) != (":" in key):
            continue
        if status[name] is None or at >= status[name][0]:
            status[name] = (at, note)
    return status


DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_INITIALS = ("M", "T", "W", "T", "F", "S", "S")
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
OPEN_SESSION_END = 1e12
HISTORY_DAYS = 30
WEEK_AVG_DAYS = 28
NONE_YET = "none yet"
REACHED = "reached"


def _day_label(day: date) -> str:
    return f"{DAY_NAMES[day.weekday()]} {day.day} {MONTH_NAMES[day.month - 1]}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def duration_text(days: float) -> str:
    if days < 60:
        return _plural(max(1, round(days)), "day")
    if days < 730:
        return _plural(round(days / 30.4375), "month")
    total_months = round(days / 30.4375)
    years, months = divmod(total_months, 12)
    text = _plural(years, "year")
    return f"{text} {_plural(months, 'month')}" if months else text


def projection_line(quest: Quest, position: Position, metres_per_step: float,
                    pace: float | None) -> str:
    if position.next is None:
        return "You stand at the Crack of Doom."
    road_left = round(quest.waypoints[-1].road_miles - road_miles_walked(position))
    head = f"{road_left:,} road miles to the Crack of Doom."
    if pace is None:
        return f"{head} Your first walk sets the pace."
    walkable_left = quest.total_walkable_miles - _miles(position)
    days = miles_to_steps(walkable_left, metres_per_step) / pace
    return f"{head} About {duration_text(days)} at your pace."


@dataclass(frozen=True)
class WalkSummary:
    live: bool
    start: float
    steps: float
    minutes: float
    mean_spm: float
    max_spm: int
    reached: list[str]


def _waypoint_names(quest: Quest, ids: list[str]) -> list[str]:
    names = {w.id: w.name for w in quest.waypoints}
    return [names[i] for i in ids if i in names]


def latest_walk(store: Store, quest: Quest) -> WalkSummary | None:
    row = store.open_session()
    live = row is not None
    if row is None:
        row = store.last_session()
    if row is None:
        return None
    hi = OPEN_SESSION_END if live else row["end"]
    ids = store.waypoints_reached_between(quest.id, row["start"], hi)
    return WalkSummary(
        live=live,
        start=row["start"],
        steps=row["steps"],
        minutes=row["active_seconds"] / 60,
        mean_spm=row["mean_spm"],
        max_spm=row["max_spm"],
        reached=_waypoint_names(quest, ids),
    )


def start_pill(start: float, today: date) -> str:
    moment = datetime.fromtimestamp(start)
    day = moment.date()
    if day == today:
        return f"today {moment:%H:%M}"
    if day == today - timedelta(days=1):
        return f"yesterday {moment:%H:%M}"
    return _day_label(day)


@dataclass(frozen=True)
class WeekStats:
    last7: list[float]
    labels: list[str]
    this_week: float
    last_week: float
    best_day: tuple[date, float] | None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_stats(store: Store, today: date) -> WeekStats:
    days = [today - timedelta(days=n) for n in range(6, -1, -1)]
    last7 = [store.steps_on_day(d) for d in days]
    monday = _monday(today)
    this_week = sum(store.steps_on_day(monday + timedelta(days=n))
                    for n in range((today - monday).days + 1))
    last_week = sum(store.steps_on_day(monday - timedelta(days=n)) for n in range(1, 8))
    best = max(zip(days, last7), key=lambda item: item[1])
    return WeekStats(
        last7=last7,
        labels=[DAY_INITIALS[d.weekday()] for d in days],
        this_week=this_week,
        last_week=last_week,
        best_day=best if best[1] > 0 else None,
    )


def week_line(w: WeekStats) -> str:
    line = f"This week {format_steps(w.this_week)} steps · last week {format_steps(w.last_week)}"
    if w.best_day is None:
        return line
    day, steps = w.best_day
    return f"{line} · best day {format_steps(steps)} ({DAY_NAMES[day.weekday()]})"


@dataclass(frozen=True)
class Records:
    records: list[tuple[str, str]]
    totals: list[tuple[str, str]]
    pace: list[tuple[str, str]]


def _number(value: float) -> str:
    if value == 0:
        return "0"
    if value < 10:
        return f"{value:.2f}"
    if value < 100:
        return f"{value:.1f}"
    return f"{value:,.0f}"


def _minutes_text(minutes: float) -> str:
    total = round(minutes)
    if total < 60:
        return f"{total} min"
    hours, rest = divmod(total, 60)
    return f"{hours} h {rest:02d} min"


def _longest_streak(days: set[date]) -> int:
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue
        run = 1
        while day + timedelta(days=run) in days:
            run += 1
        best = max(best, run)
    return best


def _daily_totals(sessions) -> dict[date, float]:
    totals: dict[date, float] = defaultdict(float)
    for row in sessions:
        totals[datetime.fromtimestamp(row["start"]).date()] += row["steps"]
    return totals


def _record_rows(sessions, daily: dict[date, float]) -> list[tuple[str, str]]:
    labels = ["Best day", "Longest walk", "Fastest walk", "Peak cadence",
              "Longest streak", "Best week", "Earliest start"]
    if not sessions:
        return [(label, NONE_YET) for label in labels]
    best_day, best_steps = max(daily.items(), key=lambda item: item[1])
    longest = max(sessions, key=lambda r: r["steps"])
    weeks: dict[date, float] = defaultdict(float)
    for day, steps in daily.items():
        weeks[_monday(day)] += steps
    best_week, week_steps = max(weeks.items(), key=lambda item: item[1])
    earliest = min(datetime.fromtimestamp(r["start"]).time() for r in sessions)
    values = [
        f"{format_steps(best_steps)} steps · {_day_label(best_day)}",
        f"{format_steps(longest['steps'])} steps · "
        f"{_minutes_text(longest['active_seconds'] / 60)}",
        f"{max(r['mean_spm'] for r in sessions):.0f} spm mean",
        f"{max(r['max_spm'] for r in sessions)} spm",
        _plural(_longest_streak(set(daily)), "day"),
        f"{format_steps(week_steps)} steps · week of {_day_label(best_week)}",
        f"{earliest:%H:%M}",
    ]
    return list(zip(labels, values))


def _total_rows(store: Store, quest: Quest, position: Position, metres_per_step: float,
                today: date, sessions, daily: dict[date, float]) -> list[tuple[str, str]]:
    steps = sum(r["steps"] for r in sessions)
    km = steps * metres_per_step / 1000
    if sessions:
        first = datetime.fromtimestamp(store.first_session_start()).date()
        walking_days = f"{len(daily)} of {(today - first).days + 1} since start"
    else:
        walking_days = "0"
    reached = quest.waypoints.index(position.reached) + 1
    chapters = [c for v in quest.volumes for p in v.parts for c in p.chapters]
    done = sum(1 for c in chapters if chapter_state(c, position) == "done")
    return [
        ("Steps", format_steps(steps)),
        ("Distance", f"{_number(km)} km, {_number(road_miles_walked(position))} road miles"),
        ("Walks", str(len(sessions))),
        ("Time walking", _minutes_text(sum(r["active_seconds"] for r in sessions) / 60)),
        ("Walking days", walking_days),
        ("Waypoints reached", f"{reached} of {len(quest.waypoints)}"),
        ("Chapters done", f"{done} of {len(chapters)}"),
    ]


def _pace_rows(store: Store, quest: Quest, position: Position, metres_per_step: float,
               today: date, sessions) -> list[tuple[str, str]]:
    pace = pace_steps_per_day(store, today) if sessions else None
    here = _miles(position)

    def until(target_miles: float) -> str:
        if target_miles <= here:
            return REACHED
        if pace is None:
            return NONE_YET
        return duration_text(miles_to_steps(target_miles - here, metres_per_step) / pace)

    if position.next is None:
        next_text = REACHED
    else:
        to_next = miles_to_steps(position.miles_to_next, metres_per_step)
        next_text = f"{format_steps(to_next)} steps"
        mean_walk = sum(r["steps"] for r in sessions) / len(sessions) if sessions else 0
        if mean_walk > 0:
            next_text += f", about {_plural(math.ceil(to_next / mean_walk), 'walk')}"

    if sessions:
        per_day = f"{format_steps(pace)} steps"
        recent = store.recent_daily_steps(WEEK_AVG_DAYS, today)
        per_week = f"{format_steps(sum(recent) / (WEEK_AVG_DAYS / 7))} steps"
    else:
        per_day = per_week = NONE_YET

    rows = [
        ("Per walking day", per_day),
        ("Per week 4-wk avg", per_week),
        ("Next waypoint", next_text),
        ("End of chapter", until(position.chapter.waypoints[-1].walkable_miles)),
    ]
    rivendell = next((w for w in quest.waypoints if w.name.startswith("Rivendell")), None)
    if rivendell is not None:
        rows.append(("Rivendell", until(rivendell.walkable_miles)))
    rows.append(("Mount Doom", until(quest.total_walkable_miles)))
    share = road_miles_walked(position) / quest.waypoints[-1].road_miles
    rows.append(("Frodo's pace", f"you are at {share:.1%} of his 6 months"))
    return rows


def records(store: Store, quest: Quest, position: Position, metres_per_step: float,
            today: date) -> Records:
    sessions = store.all_sessions()
    daily = _daily_totals(sessions)
    return Records(
        records=_record_rows(sessions, daily),
        totals=_total_rows(store, quest, position, metres_per_step, today, sessions, daily),
        pace=_pace_rows(store, quest, position, metres_per_step, today, sessions),
    )


@dataclass(frozen=True)
class DayRow:
    day: date
    steps: float
    walks: int
    minutes: float
    mean_spm: float
    reached: list[str]


def history_days(store: Store, quest: Quest, today: date,
                 days: int = HISTORY_DAYS) -> list[DayRow]:
    first_start = store.first_session_start()
    if first_start is None:
        return []
    first = datetime.fromtimestamp(first_start).date()
    rows = []
    for n in range(days):
        day = today - timedelta(days=n)
        if day < first:
            break
        stats = today_stats(store, day)
        lo = datetime.combine(day, datetime.min.time()).timestamp()
        hi = datetime.combine(day + timedelta(days=1), datetime.min.time()).timestamp()
        # waypoints_reached_between is inclusive, so stop just short of midnight
        ids = store.waypoints_reached_between(quest.id, lo, hi - 1e-6)
        rows.append(DayRow(day, stats.steps, stats.sessions, stats.minutes, stats.mean_spm,
                           _waypoint_names(quest, ids)))
    return rows


def walking_days_text(rows: list[DayRow]) -> str:
    walking = sum(1 for r in rows if r.steps > 0)
    return f"Last 30 days. Walking days {walking} of {len(rows)}."
