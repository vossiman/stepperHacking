"""BLE connection to the stepper: a reconnecting asyncio loop and its Qt thread."""

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Sequence

from bleak import BleakClient, BleakScanner
from PySide6.QtCore import QThread, Signal

from stepper_quests.frames_log import FrameLog
from stepper_quests.protocol import (
    INIT_SEQUENCE,
    NOTIFY_UUID,
    POLL,
    POLL_INTERVAL,
    WRITE_UUID,
    parse_cadence,
)

BACKOFF: tuple[float, ...] = (1, 2, 4, 8, 15)  # the last delay repeats forever
SETTLE_DELAY = 1.0
INIT_GAP = 0.25
FRAME_TIMEOUT = 10.0  # seconds without a metrics frame before the link counts as dead


async def _until_stopped(aw: Awaitable, stop_event: asyncio.Event):
    """Await `aw` and return its result, or None once `stop_event` cancels it."""
    task = asyncio.ensure_future(aw)
    waiter = asyncio.ensure_future(stop_event.wait())
    try:
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in (task, waiter):
            if not t.done():
                t.cancel()
        # Let a cancelled session run its `async with` exit so the link is closed.
        await asyncio.gather(task, waiter, return_exceptions=True)
    if task.cancelled():
        return None
    return task.result()


async def wait_for_advertisement(address: str, stop_event: asyncio.Event):
    """Scan until `address` advertises; return its BLEDevice, or None if stopped.

    There is no timeout: the console only advertises while awake, so this
    waits as long as it sleeps. Bleak prefers a BLEDevice over an address for
    BleakClient, since an address makes connect() run its own discovery first.
    """
    target = address.upper()
    seen = asyncio.Event()
    found = None

    def on_advertisement(device, _adv) -> None:
        nonlocal found
        if found is None and device.address.upper() == target:
            found = device
            seen.set()

    async with BleakScanner(detection_callback=on_advertisement):
        await _until_stopped(seen.wait(), stop_event)
    return found


async def _session(client_factory, handle_frame, on_connected, frame_age, stop_event, sleep):
    async with client_factory() as client:
        await sleep(SETTLE_DELAY)
        await client.start_notify(NOTIFY_UUID, handle_frame)
        try:
            for frame in INIT_SEQUENCE:
                await client.write_gatt_char(WRITE_UUID, frame, response=False)
                await sleep(INIT_GAP)
            on_connected()
            while not stop_event.is_set() and client.is_connected:
                await client.write_gatt_char(WRITE_UUID, POLL, response=False)
                await sleep(POLL_INTERVAL)
                if frame_age() > FRAME_TIMEOUT:
                    raise TimeoutError(f"no metrics frame for {FRAME_TIMEOUT:g} s")
        finally:
            if client.is_connected:
                with contextlib.suppress(Exception):
                    await client.stop_notify(NOTIFY_UUID)


async def run_session(
    client_factory: Callable,
    on_cadence: Callable[[int, float], None],
    on_state: Callable[[str], None],
    stop_event: asyncio.Event,
    *,
    backoff: Sequence[float] | None = None,
    sleep: Callable[[float], Awaitable] = asyncio.sleep,
    on_frame: Callable[[float, bytes], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    address: str = "",
    wait_for_device: Callable[[str, asyncio.Event], Awaitable] | None = None,
) -> None:
    """Wait for an advertisement, connect, init, poll; repeat until `stop_event` is set.

    The console sleeps after a while, drops the link and stops advertising;
    that is normal. Each round first waits for `address` to advertise, then
    connects at once with what `wait_for_device` returned, so the first steps
    after a wake are counted. Any failure, including a connect that fails
    right after the advertisement, sleeps the backoff before waiting again.
    A link that stays up but sends no metrics frame for FRAME_TIMEOUT seconds
    is treated as dead.
    """
    # Looked up per call, not bound as a default, so tests can swap the scanner.
    wait = wait_for_device or wait_for_advertisement
    delays = list(backoff) if backoff is not None else list(BACKOFF)
    attempt = 0
    state = None
    got_frame = False
    last_metrics = 0.0
    frame_log_failed = False

    def set_state(new: str) -> None:
        nonlocal state
        if new != state:
            state = new
            on_state(new)

    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    def on_connected() -> None:
        nonlocal last_metrics
        last_metrics = clock()
        set_state("connected")

    def handle_frame(_sender, data: bytearray) -> None:
        nonlocal got_frame, last_metrics, frame_log_failed
        got_frame = True
        frame = bytes(data)
        t = time.time()
        spm = parse_cadence(frame)
        if spm is not None:
            last_metrics = clock()
            on_cadence(spm, t)
        if on_frame is not None:
            # Raw logging is a debugging aid; a full disk must not stop counting.
            try:
                on_frame(t, frame)
            except Exception as exc:  # noqa: BLE001
                if not frame_log_failed:
                    frame_log_failed = True
                    log(f"frame log failed ({type(exc).__name__}: {exc}), "
                        "raw frames are no longer saved")

    while not stop_event.is_set():
        set_state("disconnected")
        got_frame = False
        try:
            log(f"waiting for {address or 'the stepper'} to advertise")
            device = await _until_stopped(wait(address, stop_event), stop_event)
            if stop_event.is_set():
                break
            log(f"{address or 'stepper'} seen, connecting")
            set_state("connecting")
            await _until_stopped(
                _session(lambda: client_factory(device), handle_frame, on_connected,
                         lambda: clock() - last_metrics, stop_event, sleep),
                stop_event,
            )
            reason = "link closed"
        except Exception as exc:  # noqa: BLE001 - any BLE failure means retry
            reason = f"{type(exc).__name__}: {exc}"
        set_state("disconnected")
        if stop_event.is_set():
            break
        if got_frame:
            attempt = 0
        delay = delays[min(attempt, len(delays) - 1)]
        attempt += 1
        log(f"disconnected ({reason}), retrying in {delay:g} s")
        await _until_stopped(sleep(delay), stop_event)


class BleWorker(QThread):
    state_changed = Signal(str)
    cadence = Signal(int, float)
    log = Signal(str)

    def __init__(self, address: str, frame_log: FrameLog | None = None, parent=None):
        super().__init__(parent)
        self.address = address
        self.frame_log = frame_log
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._stop_requested = False

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._stop_event = asyncio.Event()
        self._loop = loop
        # stop() sets the flag before reading _loop; we set _loop before
        # reading the flag, so a stop() racing startup is never lost.
        if self._stop_requested:
            self._stop_event.set()
        try:
            loop.run_until_complete(run_session(
                BleakClient,
                self.cadence.emit,
                self.state_changed.emit,
                self._stop_event,
                on_frame=self.frame_log.write_frame if self.frame_log else None,
                on_log=self.log.emit,
                address=self.address,
            ))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            self._loop = None
            loop.close()

    def stop(self, timeout_ms: int = -1) -> bool:
        """Ask the loop to stop; returns False if the thread outlived ``timeout_ms``."""
        self._stop_requested = True
        loop, event = self._loop, self._stop_event
        if loop is not None and event is not None:
            with contextlib.suppress(RuntimeError):  # loop already closed
                loop.call_soon_threadsafe(event.set)
        return self.wait() if timeout_ms < 0 else self.wait(timeout_ms)
