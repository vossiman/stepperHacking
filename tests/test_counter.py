import pytest

from stepper_quests.counter import (
    SessionEnded,
    SessionProgress,
    SessionStarted,
    SessionTracker,
    StepIntegrator,
)


def frames(tracker, spm, start, stop, step=0.5):
    events = []
    t = start
    while t < stop:
        events += tracker.feed(spm, t)
        t += step
    return events


def of_type(events, cls):
    return [e for e in events if isinstance(e, cls)]


def test_integrates_steady_cadence():
    integ = StepIntegrator()
    for i in range(121):
        integ.feed(60, i * 0.5)
    assert integ.steps == pytest.approx(60, abs=1)


def test_gap_capped_at_two_seconds():
    integ = StepIntegrator()
    assert integ.feed(60, 0.0) == 0
    assert integ.feed(60, 600.0) == 2.0


def test_session_starts_on_first_nonzero():
    tracker = SessionTracker()
    assert tracker.feed(0, 0.0) == []
    assert tracker.current is None
    events = tracker.feed(80, 1.0)
    started = of_type(events, SessionStarted)
    assert len(started) == 1
    assert started[0].session.start == 1.0
    assert tracker.current is started[0].session
    assert of_type(events, SessionProgress)


def test_session_ends_after_idle_timeout_via_tick():
    tracker = SessionTracker()
    frames(tracker, 60, 0.0, 60.0)
    assert tracker.tick(100.0) == []
    events = tracker.tick(119.5)
    ended = of_type(events, SessionEnded)
    assert len(ended) == 1
    assert ended[0].discarded is False
    assert ended[0].session.steps == pytest.approx(59.5, abs=1)
    assert tracker.current is None


def test_short_session_discarded():
    tracker = SessionTracker()
    frames(tracker, 60, 0.0, 10.0)
    events = tracker.tick(200.0)
    ended = of_type(events, SessionEnded)
    assert len(ended) == 1
    assert ended[0].discarded is True


def test_session_survives_gap():
    tracker = SessionTracker()
    events = frames(tracker, 60, 0.0, 10.0)
    events += tracker.tick(30.0)
    events += frames(tracker, 60, 30.0, 40.0)
    assert len(of_type(events, SessionStarted)) == 1
    assert of_type(events, SessionEnded) == []
    assert tracker.current.start == 0.0


def test_end_time_is_last_nonzero():
    tracker = SessionTracker()
    events = frames(tracker, 100, 0.0, 30.0)
    events += frames(tracker, 0, 30.0, 100.0)
    ended = of_type(events, SessionEnded)
    assert len(ended) == 1
    assert ended[0].session.end == 29.5


def test_new_session_after_end():
    tracker = SessionTracker()
    frames(tracker, 60, 0.0, 30.0)
    tracker.tick(200.0)
    events = tracker.feed(70, 201.0)
    started = of_type(events, SessionStarted)
    assert len(started) == 1
    assert started[0].session.start == 201.0
    assert started[0].session.steps == 0


def test_session_stats():
    tracker = SessionTracker()
    tracker.feed(60, 0.0)
    tracker.feed(100, 1.0)
    tracker.feed(0, 2.0)
    s = tracker.current
    assert s.max_spm == 100
    assert s.mean_spm == 80
    assert s.active_seconds == 1.0
    assert s.steps == pytest.approx(100 / 60)


def test_finish_ends_running_session_at_last_nonzero():
    tracker = SessionTracker(min_steps=20)
    frames(tracker, 100, 0.0, 30.0)
    frames(tracker, 0, 30.0, 40.0)
    events = tracker.finish()
    assert len(events) == 1
    assert isinstance(events[0], SessionEnded)
    assert events[0].session.end == 29.5
    assert not events[0].discarded
    assert tracker.current is None


def test_finish_discards_short_session():
    tracker = SessionTracker(min_steps=20)
    frames(tracker, 60, 0.0, 5.0)
    events = tracker.finish()
    assert events[0].discarded


def test_finish_without_session_is_empty():
    assert SessionTracker().finish() == []
