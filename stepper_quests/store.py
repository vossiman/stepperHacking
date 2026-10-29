import json
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start REAL NOT NULL,
    end REAL,
    steps REAL NOT NULL,
    max_spm INTEGER NOT NULL,
    mean_spm REAL NOT NULL,
    active_seconds REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions(start);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS achievements (
    name TEXT PRIMARY KEY,
    at REAL NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS waypoints (
    quest_id TEXT NOT NULL,
    waypoint_id TEXT NOT NULL,
    at REAL NOT NULL,
    PRIMARY KEY (quest_id, waypoint_id)
);
"""


def _day_bounds(day: date) -> tuple[float, float]:
    start = datetime.combine(day, time()).timestamp()
    end = datetime.combine(day + timedelta(days=1), time()).timestamp()
    return start, end


class Store:
    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @staticmethod
    def default_path() -> Path:
        home = os.environ.get("STEPPER_QUESTS_HOME")
        base = Path(home) if home else Path.home() / ".local/share/stepper-quests"
        base.mkdir(parents=True, exist_ok=True)
        return base / "steps.db"

    def upsert_session(
        self,
        session_id: int | None,
        start: float,
        end: float | None,
        steps: float,
        max_spm: int,
        mean_spm: float,
        active_seconds: float,
    ) -> int:
        values = (start, end, steps, max_spm, mean_spm, active_seconds)
        with self._conn:
            if session_id is None:
                cur = self._conn.execute(
                    "INSERT INTO sessions (start, end, steps, max_spm, mean_spm, active_seconds)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    values,
                )
                return cur.lastrowid
            self._conn.execute(
                "INSERT INTO sessions (id, start, end, steps, max_spm, mean_spm, active_seconds)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET start=excluded.start, end=excluded.end,"
                " steps=excluded.steps, max_spm=excluded.max_spm,"
                " mean_spm=excluded.mean_spm, active_seconds=excluded.active_seconds",
                (session_id, *values),
            )
            return session_id

    def delete_session(self, session_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def repair_sessions(self, min_steps: float) -> int:
        """Clean up rows a crash left behind; returns how many rows changed.

        Rows below ``min_steps`` are deleted, as the tracker would have
        discarded them. Rows with no end get ``start + active_seconds``.
        """
        with self._conn:
            deleted = self._conn.execute(
                "DELETE FROM sessions WHERE steps < ?", (min_steps,)
            ).rowcount
            closed = self._conn.execute(
                "UPDATE sessions SET end = start + active_seconds WHERE end IS NULL"
            ).rowcount
        return deleted + closed

    def lifetime_steps(self) -> float:
        return self._conn.execute("SELECT COALESCE(SUM(steps), 0.0) FROM sessions").fetchone()[0]

    def steps_on_day(self, day: date) -> float:
        lo, hi = _day_bounds(day)
        return self._conn.execute(
            "SELECT COALESCE(SUM(steps), 0.0) FROM sessions WHERE start >= ? AND start < ?",
            (lo, hi),
        ).fetchone()[0]

    def sessions_on_day(self, day: date) -> list[sqlite3.Row]:
        lo, hi = _day_bounds(day)
        return self._conn.execute(
            "SELECT * FROM sessions WHERE start >= ? AND start < ? ORDER BY start",
            (lo, hi),
        ).fetchall()

    def sessions_between(self, lo: float, hi: float) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM sessions WHERE start >= ? AND start < ? ORDER BY start",
            (lo, hi),
        ).fetchall()

    def open_session(self) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM sessions WHERE end IS NULL ORDER BY start DESC LIMIT 1"
        ).fetchone()

    def last_session(self) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM sessions WHERE end IS NOT NULL ORDER BY start DESC LIMIT 1"
        ).fetchone()

    def first_session_start(self) -> float | None:
        row = self._conn.execute("SELECT MIN(start) FROM sessions").fetchone()
        return row[0]

    def all_sessions(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM sessions ORDER BY start").fetchall()

    def _daily_totals(self) -> dict[date, float]:
        totals: dict[date, float] = defaultdict(float)
        for start, steps in self._conn.execute("SELECT start, steps FROM sessions"):
            totals[datetime.fromtimestamp(start).date()] += steps
        return totals

    def best_day(self) -> tuple[date, float] | None:
        totals = self._daily_totals()
        if not totals:
            return None
        return max(totals.items(), key=lambda item: item[1])

    def longest_session_steps(self) -> float:
        return self._conn.execute("SELECT COALESCE(MAX(steps), 0.0) FROM sessions").fetchone()[0]

    def streak_days(self, today: date) -> int:
        days = set(self._daily_totals())
        day = today if today in days else today - timedelta(days=1)
        streak = 0
        while day in days:
            streak += 1
            day -= timedelta(days=1)
        return streak

    def recent_daily_steps(self, days: int, today: date) -> list[float]:
        return [self.steps_on_day(today - timedelta(days=n)) for n in range(days - 1, -1, -1)]

    def get_setting(self, key: str, default=None):
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def set_setting(self, key: str, value) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def unlock(self, name: str, at: float, note: str = "") -> bool:
        with self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO achievements (name, at, note) VALUES (?, ?, ?)",
                (name, at, note),
            )
        return cur.rowcount == 1

    def unlocked(self) -> list[tuple[str, float, str]]:
        rows = self._conn.execute("SELECT name, at, note FROM achievements ORDER BY at")
        return [tuple(row) for row in rows]

    def mark_waypoint(self, quest_id: str, waypoint_id: str, at: float) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO waypoints (quest_id, waypoint_id, at) VALUES (?, ?, ?)",
                (quest_id, waypoint_id, at),
            )

    def reached_waypoints(self, quest_id: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT waypoint_id FROM waypoints WHERE quest_id = ?", (quest_id,)
        )
        return {row[0] for row in rows}

    def waypoints_reached_between(self, quest_id: str, lo: float, hi: float) -> list[str]:
        rows = self._conn.execute(
            "SELECT waypoint_id FROM waypoints"
            " WHERE quest_id = ? AND at >= ? AND at <= ? ORDER BY at",
            (quest_id, lo, hi),
        )
        return [row[0] for row in rows]

    def close(self) -> None:
        self._conn.close()
