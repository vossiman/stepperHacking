import asyncio
import csv
import threading
import time
from pathlib import Path

import pytest

from stepper_quests import ble
from stepper_quests.ble import run_session
from stepper_quests.ble import wait_for_advertisement as real_wait
from stepper_quests.frames_log import FrameLog
from stepper_quests.protocol import INIT_SEQUENCE, NOTIFY_UUID, POLL, WRITE_UUID

FIXTURE = Path(__file__).parent / "fixtures" / "frames.csv"
NON_METRICS = bytes.fromhex("f0b000c868")


def b2(spm: int) -> bytes:
    body = bytearray(18)
    body[0], body[1], body[3], body[9] = 0xF0, 0xB2, 0xC8, spm
    return bytes(body) + bytes([sum(body) & 0xFF])


def recorded_b2_frames() -> list[bytes]:
    with FIXTURE.open() as f:
        rows = list(csv.DictReader(f))
    return [bytes.fromhex(r["hex"]) for r in rows if r["hex"].startswith("f0b2")]


class FakeClient:
    """Emits one scripted frame per poll; may raise on the Nth poll."""

    def __init__(self, events, frames=(), fail_on_poll=None, stop_on_poll=None,
                 stop_event=None, fail_connect=False):
        self.events = events
        self.frames = list(frames)
        self.fail_on_poll = fail_on_poll
        self.stop_on_poll = stop_on_poll
        self.stop_event = stop_event
        self.fail_connect = fail_connect
        self.is_connected = False
        self.callback = None
        self.polls = 0
        self.writes = 0

    async def __aenter__(self):
        if self.fail_connect:
            self.events.append(("connect_failed",))
            raise OSError("device not found")
        self.is_connected = True
        return self

    async def __aexit__(self, *exc):
        self.is_connected = False
        self.events.append(("exit",))

    async def start_notify(self, uuid, callback):
        self.events.append(("start_notify", uuid))
        self.callback = callback

    async def stop_notify(self, uuid):
        self.events.append(("stop_notify", uuid))

    async def write_gatt_char(self, uuid, data, response=False):
        self.events.append(("write", uuid, bytes(data), response))
        self.writes += 1
        if self.writes <= len(INIT_SEQUENCE):
            return
        self.polls += 1
        if self.polls == self.fail_on_poll:
            raise OSError("link lost")
        if self.frames:
            self.callback(None, bytearray(self.frames.pop(0)))
        if self.polls == self.stop_on_poll:
            self.stop_event.set()


def make_sleep(record, stop_event=None, stop_after_backoffs=None, min_backoff=10):
    async def fake_sleep(delay):
        record.append(delay)
        backoffs = [d for d in record if d >= min_backoff]
        if stop_after_backoffs and len(backoffs) >= stop_after_backoffs:
            stop_event.set()
        await asyncio.sleep(0)

    return fake_sleep


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=5))


async def instant_wait(address, stop_event):
    await asyncio.sleep(0)
    return address


@pytest.fixture(autouse=True)
def no_real_scanner(monkeypatch):
    """No test may start a real BleakScanner; the device is 'seen' at once."""
    monkeypatch.setattr(ble, "wait_for_advertisement", instant_wait)


def test_init_then_poll_sequence():
    events, states, sleeps = [], [], []

    async def main():
        stop = asyncio.Event()
        client = FakeClient(events, stop_on_poll=3, stop_event=stop)
        await run_session(
            lambda _device: client,
            lambda spm, t: None,
            lambda s: (states.append(s), events.append(("state", s))),
            stop,
            sleep=make_sleep(sleeps),
        )

    run(main())

    write_pos = [i for i, e in enumerate(events) if e[0] == "write"]
    writes = [events[i] for i in write_pos]
    assert [w[2] for w in writes] == INIT_SEQUENCE + [POLL] * 3
    assert all(w[1] == WRITE_UUID and w[3] is False for w in writes)
    assert events.index(("start_notify", NOTIFY_UUID)) < write_pos[0]
    connected = events.index(("state", "connected"))
    assert write_pos[len(INIT_SEQUENCE) - 1] < connected < write_pos[len(INIT_SEQUENCE)]
    assert states == ["disconnected", "connecting", "connected", "disconnected"]
    assert ("stop_notify", NOTIFY_UUID) in events
    assert events[-1] == ("state", "disconnected")


def test_cadence_emitted():
    events, cadences, frames_seen = [], [], []
    recorded = recorded_b2_frames()
    assert recorded, "fixture has no B2 frames"
    script = [b2(60), NON_METRICS, b2(1), recorded[0]]

    async def main():
        stop = asyncio.Event()
        client = FakeClient(events, frames=script, stop_on_poll=len(script),
                            stop_event=stop)
        await run_session(
            lambda _device: client,
            lambda spm, t: cadences.append((spm, t)),
            lambda s: None,
            stop,
            sleep=make_sleep([]),
            on_frame=lambda t, data: frames_seen.append(data),
        )

    before = time.time()
    run(main())
    after = time.time()

    expected_last = 0 if recorded[0][9] <= 1 else recorded[0][9]
    assert [spm for spm, _ in cadences] == [60, 0, expected_last]
    assert all(isinstance(t, float) and before <= t <= after for _, t in cadences)
    assert frames_seen == script


def test_exception_leads_to_disconnected_and_retry():
    events, states, sleeps = [], [], []
    made = []

    async def main():
        stop = asyncio.Event()
        clients = [
            FakeClient(events, frames=[b2(50)] * 5, fail_on_poll=2),
            FakeClient(events, frames=[b2(70)], stop_on_poll=1, stop_event=stop),
        ]

        def factory(_device):
            made.append(1)
            return clients[len(made) - 1]

        await run_session(
            factory,
            lambda spm, t: None,
            states.append,
            stop,
            backoff=[10, 20, 40],
            sleep=make_sleep(sleeps),
        )

    run(main())

    assert len(made) == 2
    assert states == ["disconnected"] + ["connecting", "connected", "disconnected"] * 2
    assert [d for d in sleeps if d >= 10] == [10]


def test_backoff_sequence():
    events, states, sleeps = [], [], []

    async def main():
        stop = asyncio.Event()
        await run_session(
            lambda _device: FakeClient(events, fail_connect=True),
            lambda spm, t: None,
            states.append,
            stop,
            sleep=make_sleep(sleeps, stop, stop_after_backoffs=7, min_backoff=1),
        )

    run(main())

    assert sleeps == [1, 2, 4, 8, 15, 15, 15]
    assert states == ["disconnected"] + ["connecting", "disconnected"] * 7
    assert "connected" not in states


def test_backoff_resets_after_session_with_frames():
    events, sleeps = [], []
    calls = []

    async def main():
        stop = asyncio.Event()

        def factory(_device):
            calls.append(1)
            n = len(calls)
            if n == 3:
                return FakeClient(events, frames=[b2(55)], fail_on_poll=2)
            return FakeClient(events, fail_connect=True)

        await run_session(
            factory,
            lambda spm, t: None,
            lambda s: None,
            stop,
            backoff=[10, 20, 40],
            sleep=make_sleep(sleeps, stop, stop_after_backoffs=4),
        )

    run(main())

    assert [d for d in sleeps if d >= 10] == [10, 20, 10, 20]


def test_stop_interrupts_backoff_sleep():
    async def main():
        stop = asyncio.Event()
        task = asyncio.ensure_future(run_session(
            lambda _device: FakeClient([], fail_connect=True),
            lambda spm, t: None,
            lambda s: None,
            stop,
            backoff=[3600],
        ))
        await asyncio.sleep(0.05)
        stop.set()
        await task

    started = time.monotonic()
    run(main())
    assert time.monotonic() - started < 2


def test_frame_log_writes_csvs(tmp_path):
    log = FrameLog(tmp_path)
    log.open_session()
    log.write_frame(1.5, bytes.fromhex("f0b000c868"))
    log.write_step(2.0, 60, 12)
    log.close()

    frames = list(tmp_path.glob("frames_*.csv"))
    steps = list(tmp_path.glob("steps_*.csv"))
    assert len(frames) == 1 and len(steps) == 1
    frame_rows = list(csv.reader(frames[0].read_text().splitlines()))
    assert frame_rows[0] == ["t", "hex", "len"] + [f"b{i}" for i in range(20)]
    assert frame_rows[1] == ["1.500", "f0b000c868", "5", "240", "176", "0", "200", "104"]
    step_rows = list(csv.reader(steps[0].read_text().splitlines()))
    assert step_rows == [["t", "spm", "total_steps"], ["2.000", "60", "12"]]


def test_frame_log_default_dir(home_dir, monkeypatch, tmp_path):
    assert FrameLog.default_dir() == home_dir / "data"
    monkeypatch.delenv("STEPPER_QUESTS_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    assert FrameLog.default_dir() == tmp_path / "h" / ".local/share/stepper-quests/data"


def test_worker_retries_and_stops(monkeypatch, tmp_path):
    from PySide6.QtCore import QCoreApplication, Qt

    app = QCoreApplication.instance() or QCoreApplication([])

    class FailingClient(FakeClient):
        def __init__(self, address):
            assert address == "AA:BB"
            super().__init__([], fail_connect=True)

    monkeypatch.setattr(ble, "BleakClient", FailingClient)
    states = []
    disconnected = threading.Event()

    def on_state(s):
        states.append(s)
        if s == "disconnected" and "connecting" in states:
            disconnected.set()

    worker = ble.BleWorker("AA:BB", frame_log=FrameLog(tmp_path))
    worker.state_changed.connect(on_state, Qt.DirectConnection)
    worker.start()
    assert disconnected.wait(5)
    started = time.monotonic()
    worker.stop()
    assert time.monotonic() - started < 2
    assert worker.isFinished()
    assert states[:3] == ["disconnected", "connecting", "disconnected"]
    assert app is not None


def test_silent_link_times_out_and_reconnects():
    events, states, sleeps = [], [], []
    made = []
    now = [0.0]

    async def clock_sleep(delay):
        sleeps.append(delay)
        now[0] += delay
        await asyncio.sleep(0)

    async def main():
        stop = asyncio.Event()
        # Connected and polled, but frames stop after two: the link is dead.
        silent = FakeClient(events, frames=[b2(60), b2(60)])
        second = FakeClient(events, frames=[b2(70)], stop_on_poll=1, stop_event=stop)
        clients = [silent, second]

        def factory(_device):
            made.append(1)
            return clients[len(made) - 1]

        await run_session(
            factory,
            lambda spm, t: None,
            states.append,
            stop,
            backoff=[100],
            sleep=clock_sleep,
            clock=lambda: now[0],
        )
        return silent

    silent = run(main())

    assert len(made) == 2
    assert states == ["disconnected"] + ["connecting", "connected", "disconnected"] * 2
    assert 100 in sleeps
    # Two polls answered, then about FRAME_TIMEOUT / POLL_INTERVAL silent polls.
    expected = 2 + ble.FRAME_TIMEOUT / ble.POLL_INTERVAL
    assert expected - 1 <= silent.polls <= expected + 1


def test_frame_log_failure_does_not_block_cadence():
    events, cadences, logs, states = [], [], [], []
    script = [b2(60), b2(62), b2(64)]

    def broken_log(t, data):
        raise OSError("No space left on device")

    async def main():
        stop = asyncio.Event()
        client = FakeClient(events, frames=script, stop_on_poll=len(script),
                            stop_event=stop)
        await run_session(
            lambda _device: client,
            lambda spm, t: cadences.append(spm),
            states.append,
            stop,
            sleep=make_sleep([]),
            on_frame=broken_log,
            on_log=logs.append,
        )

    run(main())

    assert cadences == [60, 62, 64]
    assert states == ["disconnected", "connecting", "connected", "disconnected"]
    frame_log_lines = [line for line in logs if "No space left" in line]
    assert len(frame_log_lines) == 1


def test_frame_log_drops_writes_after_close(tmp_path):
    log = FrameLog(tmp_path)
    log.open_session()
    log.close()
    log.write_frame(1.0, b"\xf0")
    log.write_step(1.0, 60, 1)
    assert len(list(tmp_path.glob("frames_*.csv"))) == 1
    assert len(list(tmp_path.glob("steps_*.csv"))) == 1
    assert all(len(p.read_text().splitlines()) == 1 for p in tmp_path.glob("*.csv"))


def test_waits_for_advertisement_before_each_connect():
    events, states = [], []
    devices = []

    async def wait(address, stop_event):
        events.append(("wait", address))
        await asyncio.sleep(0)
        return f"device-{len(devices)}"

    async def recording_sleep(delay):
        events.append(("sleep", delay))
        await asyncio.sleep(0)

    async def main():
        stop = asyncio.Event()
        clients = [
            FakeClient(events, frames=[b2(50)] * 5, fail_on_poll=2),
            FakeClient(events, frames=[b2(70)], stop_on_poll=1, stop_event=stop),
        ]

        def factory(device):
            devices.append(device)
            events.append(("connect", device))
            return clients[len(devices) - 1]

        await run_session(
            factory,
            lambda spm, t: None,
            lambda s: (states.append(s), events.append(("state", s))),
            stop,
            address="AA:BB",
            backoff=[10],
            sleep=recording_sleep,
            wait_for_device=wait,
        )

    run(main())

    assert devices == ["device-0", "device-1"]
    connects = [i for i, e in enumerate(events) if e[0] == "connect"]
    waits = [i for i, e in enumerate(events) if e[0] == "wait"]
    assert len(waits) == 2 and all(e[1] == "AA:BB" for e in (events[i] for i in waits))
    for w, c in zip(waits, connects):
        between = events[w + 1:c]
        assert w < c
        assert not [e for e in between if e[0] == "sleep"]
        assert between == [("state", "connecting")]
    # The backoff sleep sits before the second wait, never between wait and connect.
    backoff = events.index(("sleep", 10))
    assert connects[0] < backoff < waits[1]
    assert states[0] == "disconnected"


def test_stop_during_wait_ends_promptly():
    states = []
    connects = []

    async def never_seen(address, stop_event):
        await asyncio.Event().wait()  # ignores stop_event on purpose

    async def main():
        stop = asyncio.Event()
        task = asyncio.ensure_future(run_session(
            lambda device: connects.append(device),
            lambda spm, t: None,
            states.append,
            stop,
            address="AA:BB",
            wait_for_device=never_seen,
        ))
        await asyncio.sleep(0.05)
        assert not task.done()
        stop.set()
        await task

    started = time.monotonic()
    run(main())
    assert time.monotonic() - started < 2
    assert connects == []
    assert states == ["disconnected"]


def test_connect_error_after_advertisement_backs_off_then_waits():
    events, states, logs = [], [], []
    made = []

    async def wait(address, stop_event):
        events.append(("wait",))
        await asyncio.sleep(0)
        return address

    async def recording_sleep(delay):
        events.append(("sleep", delay))
        await asyncio.sleep(0)

    async def main():
        stop = asyncio.Event()
        clients = [
            FakeClient(events, fail_connect=True),
            FakeClient(events, frames=[b2(70)], stop_on_poll=1, stop_event=stop),
        ]

        def factory(device):
            made.append(device)
            return clients[len(made) - 1]

        await run_session(
            factory,
            lambda spm, t: None,
            states.append,
            stop,
            address="AA:BB",
            backoff=[10, 20],
            sleep=recording_sleep,
            wait_for_device=wait,
            on_log=logs.append,
        )

    run(main())

    flow = [e for e in events if e[0] in ("wait", "connect_failed") or e == ("sleep", 10)
            or e == ("sleep", 20)]
    assert flow == [("wait",), ("connect_failed",), ("sleep", 10), ("wait",)]
    assert made == ["AA:BB", "AA:BB"]
    assert states == ["disconnected", "connecting", "disconnected",
                      "connecting", "connected", "disconnected"]
    assert any("waiting" in line for line in logs)
    assert any("seen" in line for line in logs)


class FakeDevice:
    def __init__(self, address):
        self.address = address


class FakeScanner:
    instances = []

    def __init__(self, detection_callback=None, **kwargs):
        self.callback = detection_callback
        self.running = False
        FakeScanner.instances.append(self)

    async def __aenter__(self):
        self.running = True
        return self

    async def __aexit__(self, *exc):
        self.running = False


def test_default_wait_matches_mac_case_insensitively(monkeypatch):
    FakeScanner.instances = []
    monkeypatch.setattr(ble, "BleakScanner", FakeScanner)
    target = FakeDevice("AA:BB:CC:DD:EE:FF")

    async def main():
        stop = asyncio.Event()
        task = asyncio.ensure_future(real_wait("aa:bb:cc:dd:ee:ff", stop))
        await asyncio.sleep(0.01)
        scanner = FakeScanner.instances[0]
        assert scanner.running
        scanner.callback(FakeDevice("11:22:33:44:55:66"), None)
        await asyncio.sleep(0.01)
        assert not task.done()
        scanner.callback(target, None)
        found = await task
        return found, scanner

    found, scanner = run(main())
    assert found is target
    assert not scanner.running


def test_default_wait_returns_none_on_stop(monkeypatch):
    FakeScanner.instances = []
    monkeypatch.setattr(ble, "BleakScanner", FakeScanner)

    async def main():
        stop = asyncio.Event()
        task = asyncio.ensure_future(real_wait("AA:BB", stop))
        await asyncio.sleep(0.01)
        stop.set()
        return await task

    assert run(main()) is None
    assert not FakeScanner.instances[0].running
