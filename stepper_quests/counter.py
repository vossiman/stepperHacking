"""Step integration and session detection from cadence frames.

Pure and time-injected: every ``t`` is wall-clock seconds passed in by the caller.
"""

from dataclasses import dataclass

DT_CAP = 2.0


class StepIntegrator:
    def __init__(self) -> None:
        self.steps: float = 0.0
        self._last_t: float | None = None

    def feed(self, spm: int, t: float) -> float:
        added = 0.0
        if self._last_t is not None:
            added = spm * capped_dt(self._last_t, t) / 60
        self._last_t = t
        self.steps += added
        return added


def capped_dt(prev: float, t: float) -> float:
    return min(max(t - prev, 0.0), DT_CAP)


@dataclass
class Session:
    start: float
    end: float | None = None
    steps: float = 0.0
    max_spm: int = 0
    spm_sum: int = 0
    spm_n: int = 0
    active_seconds: float = 0.0

    @property
    def mean_spm(self) -> float:
        return self.spm_sum / self.spm_n if self.spm_n else 0.0


@dataclass
class SessionStarted:
    session: Session


@dataclass
class SessionProgress:
    session: Session


@dataclass
class SessionEnded:
    session: Session
    discarded: bool


Event = SessionStarted | SessionProgress | SessionEnded


class SessionTracker:
    def __init__(self, idle_timeout: float = 60.0, min_steps: int = 20) -> None:
        self.idle_timeout = idle_timeout
        self.min_steps = min_steps
        self.current: Session | None = None
        self._integrator = StepIntegrator()
        self._last_t: float | None = None
        self._last_nonzero_t: float = 0.0

    def feed(self, spm: int, t: float) -> list[Event]:
        events = self.tick(t)
        if self.current is None:
            if spm <= 0:
                return events
            self.current = Session(start=t)
            self._integrator = StepIntegrator()
            self._last_t = None
            events.append(SessionStarted(self.current))
        session = self.current
        session.steps += self._integrator.feed(spm, t)
        if spm > 0:
            if self._last_t is not None:
                session.active_seconds += capped_dt(self._last_t, t)
            session.max_spm = max(session.max_spm, spm)
            session.spm_sum += spm
            session.spm_n += 1
            self._last_nonzero_t = t
        self._last_t = t
        events.append(SessionProgress(session))
        return events

    def tick(self, t: float) -> list[Event]:
        session = self.current
        if session is None or t - self._last_nonzero_t < self.idle_timeout:
            return []
        return self.finish()

    def finish(self) -> list[Event]:
        """End the running session now, by the same rules as an idle timeout."""
        session = self.current
        if session is None:
            return []
        session.end = self._last_nonzero_t
        self.current = None
        return [SessionEnded(session, discarded=session.steps < self.min_steps)]
