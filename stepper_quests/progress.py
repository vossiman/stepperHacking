"""Turns stored steps into waypoint, achievement and part-completion notices."""

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from .counter import Session
from .quests import DEFAULT_METRES_PER_STEP, Quest, steps_to_miles
from .store import Store

SECOND_BREAKFAST_GAP = 7200.0
ELEVENSES_HOUR = 11
HOBBITS_PACE_DAYS = 7
RANGERS_DAYS = 30
PARTY_STEPS = 100000


@dataclass
class Settings:
    metres_per_step: float = DEFAULT_METRES_PER_STEP


@dataclass
class Notice:
    kind: str
    title: str
    body: str


def notices_to_json(notices: list[Notice]) -> list[dict]:
    return [{"title": n.title, "body": n.body, "kind": n.kind} for n in notices]


def notices_from_json(value) -> list[Notice]:
    return [Notice(d["kind"], d["title"], d["body"]) for d in value or []]


@dataclass(frozen=True)
class Achievement:
    name: str
    title: str
    body: str
    condition: str
    repeatable: bool = False


ACHIEVEMENTS = [
    Achievement(
        "second-breakfast", "Second Breakfast",
        "One walk is never enough for a hobbit.",
        "Walk twice in one day, with the walks starting at least two hours apart.",
    ),
    Achievement(
        "elevenses", "Elevenses",
        "Out on the road before the kettle goes on for elevenses.",
        "Start a walk before 11 in the morning.",
    ),
    Achievement(
        "hobbits-pace", "Hobbit's Pace",
        "A week of steady walking, the way hobbits like it.",
        f"Walk on {HOBBITS_PACE_DAYS} days in a row.",
    ),
    Achievement(
        "rangers-of-the-north", "Rangers of the North",
        "A month on the move. Strider would nod in approval.",
        f"Walk on {RANGERS_DAYS} days in a row.",
    ),
    Achievement(
        "long-expected-party", "Long-expected Party",
        "Eleventy-one cheers for your first hundred thousand steps.",
        f"Walk {PARTY_STEPS:,} steps in total.",
    ),
    Achievement(
        "sting-glows", "Sting Glows",
        "Your blade glows blue: a new best day.",
        "Beat your best daily step total.",
        repeatable=True,
    ),
    Achievement(
        "wander", "Not all those who wander",
        "Your longest walk yet, and you were never lost.",
        "Walk more steps in one session than ever before.",
        repeatable=True,
    ),
    Achievement(
        "road-goes-on", "The Road Goes Ever On",
        "Another part of the tale is behind you.",
        "Reach the end of a part of the journey.",
        repeatable=True,
    ),
]

_BY_NAME = {a.name: a for a in ACHIEVEMENTS}


class Progress:
    def __init__(self, store: Store, quest: Quest, settings: Settings):
        self.store = store
        self.quest = quest
        self.settings = settings

    def on_session_progress(self, extra_steps: float) -> list[Notice]:
        """Mark newly passed waypoints.

        ``extra_steps`` are steps not yet in the store, such as the running
        session's when it has not been upserted.
        """
        notices = []
        for index, waypoint in self._newly_reached(extra_steps):
            self.store.mark_waypoint(self.quest.id, waypoint.id, time.time())
            if index > 0:
                notices.append(Notice("waypoint", waypoint.name, waypoint.story))
        return notices

    def sync_silently(self, extra_steps: float = 0.0) -> None:
        now = time.time()
        for _, waypoint in self._newly_reached(extra_steps):
            self.store.mark_waypoint(self.quest.id, waypoint.id, now)
        # Parts finished before startup must not toast on the next session end.
        self._completed_parts(now)

    def on_session_ended(self, session: Session) -> list[Notice]:
        """Evaluate achievements; the session may or may not be stored already."""
        at = session.end if session.end is not None else session.start
        day = datetime.fromtimestamp(session.start).date()
        sessions = self._all_sessions(session)
        mine = [s for s in sessions if s[0] == session.start]
        others = [s for s in sessions if s[0] != session.start]
        starts_today = [s for s, _ in sessions if _day(s) == day]
        totals: dict[date, float] = defaultdict(float)
        for start, steps in sessions:
            totals[_day(start)] += steps
        lifetime = sum(totals.values())
        streak = self._streak(set(totals), day)

        checks = [
            ("second-breakfast", None,
             bool(starts_today) and max(starts_today) - min(starts_today) >= SECOND_BREAKFAST_GAP),
            ("elevenses", None, datetime.fromtimestamp(session.start).hour < ELEVENSES_HOUR),
            ("hobbits-pace", None, streak >= HOBBITS_PACE_DAYS),
            ("rangers-of-the-north", None, streak >= RANGERS_DAYS),
            ("long-expected-party", None, lifetime >= PARTY_STEPS),
        ]
        day_total = totals[day]
        other_days = [v for d, v in totals.items() if d != day]
        if other_days and day_total > max(other_days):
            checks.append(("sting-glows", (day.isoformat(), f"{day_total:.0f}"), True))
        steps = sum(s for _, s in mine)
        if others and steps > max(s for _, s in others):
            checks.append(("wander", (f"{int(steps)}", f"{int(steps)}"), True))

        notices = []
        for name, repeat, passed in checks:
            if not passed:
                continue
            key, note = (f"{name}:{repeat[0]}", repeat[1]) if repeat else (name, "")
            if self.store.unlock(key, at=at, note=note):
                a = _BY_NAME[name]
                notices.append(Notice("achievement", a.title, a.body))
        road = _BY_NAME["road-goes-on"]
        for label in self._completed_parts(at):
            notices.append(Notice("part", road.title, f"{label} is complete. {road.body}"))
        return notices

    def _newly_reached(self, extra_steps: float):
        lifetime = self.store.lifetime_steps() + extra_steps
        miles = steps_to_miles(lifetime, self.settings.metres_per_step)
        reached = self.store.reached_waypoints(self.quest.id)
        for index, waypoint in enumerate(self.quest.waypoints):
            if waypoint.walkable_miles > miles:
                break
            if waypoint.id not in reached:
                yield index, waypoint

    def _completed_parts(self, at: float) -> list[str]:
        reached = self.store.reached_waypoints(self.quest.id)
        done = []
        for volume in self.quest.volumes:
            for part in volume.parts:
                waypoints = [w for c in part.chapters for w in c.waypoints]
                if not waypoints or waypoints[-1].id not in reached:
                    continue
                # Part titles repeat across volumes, so the volume is part of the key.
                label = f"{volume.title} / {part.title}"
                if self.store.unlock(f"road-goes-on:{label}", at=at, note=label):
                    done.append(label)
        return done

    def _all_sessions(self, session: Session) -> list[tuple[float, float]]:
        rows = [(r["start"], r["steps"]) for r in self.store.all_sessions()]
        if not any(start == session.start for start, _ in rows):
            rows.append((session.start, session.steps))
        return rows

    @staticmethod
    def _streak(days: set[date], today: date) -> int:
        streak = 0
        day = today
        while day in days:
            streak += 1
            day = date.fromordinal(day.toordinal() - 1)
        return streak


def _day(timestamp: float) -> date:
    return datetime.fromtimestamp(timestamp).date()
