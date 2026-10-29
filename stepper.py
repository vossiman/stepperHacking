#!/usr/bin/env python3
"""
Local step counter for the Sportstech DFX100 / iConsole+ stepper over BLE.

Protocol (reverse-engineered, cross-checked against qdomyos-zwift's
iconsolebike parser and your own btsnoop capture):

  Service  FFF0
    FFF2 (write) : host -> device commands, handle ~0x0039
    FFF1 (notify): device -> host replies,  handle ~0x0036

  Frames are `F0 <op> ... <checksum>` where checksum = sum(all prior bytes) & 0xFF.
  The device is POLL-DRIVEN: it only streams the 20-byte metrics frame
  (F0 B2 ...) while the host keeps sending the poll `F0 A2 01 01 94`.

  Why earlier attempts failed: they sent bare 3-byte `f0a200` and only the
  app's full checksummed init + continuous poll unlocks the real stream.
  There is no authentication.

Usage:
  python stepper.py                 # scan, connect, count steps live
  python stepper.py --address AA:BB:CC:DD:EE:FF
  python stepper.py --raw           # calibration: print every frame + byte grid
  python stepper.py --seconds 120   # stop after N seconds (0 = until Ctrl-C)

Byte offsets for steps/spm are confirmed empirically in --raw mode; the live
decoder uses the best current hypothesis and is trivial to adjust at the top.
"""
import argparse
import asyncio
import csv
import os
import sys
import time
from datetime import datetime

from bleak import BleakClient, BleakScanner

# ---- BLE identifiers -------------------------------------------------------
SVC_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
NAME_HINTS = ("iconsole", "dfx", "fs-", "fitshow", "stepper")

# ---- Metrics-frame decode (confirmed empirically on the DFX100) ------------
# In the 19-byte `F0 B2 ...` frame, byte 9 is the ONLY live field: steps per
# minute (cadence). Byte 3 is a fixed 0xC8, byte 18 is the checksum, all other
# bytes stay 0. The console sends no cumulative step total, so we integrate the
# cadence over real elapsed time to get the running step count.
SPM_BYTE = 9
SPM_IDLE = 1          # raw values <= this mean "not stepping"


def checksum(body: bytes) -> int:
    return sum(body) & 0xFF


def framed(*body: int) -> bytes:
    b = bytes(body)
    return b + bytes([checksum(b)])


# Exact app init sequence (each already includes its checksum byte).
INIT_SEQUENCE = [
    bytes.fromhex("f0a0000090"),   # hello
    bytes.fromhex("f0a0010192"),   # init confirm
    bytes.fromhex("f0a1010193"),   # data
    bytes.fromhex("f0a50101049b"), # data
    bytes.fromhex("f0a501010299"), # data
    bytes.fromhex("f0a2010194"),   # first poll / start streaming
]
POLL = bytes.fromhex("f0a2010194")
POLL_INTERVAL = 0.5  # seconds (~2 Hz, matches the app)


class StepperSession:
    def __init__(self, raw: bool):
        self.raw = raw
        self.start = time.time()
        self.frame_count = 0
        # integrated step count
        self.steps = 0.0
        self.last_t = None
        self.spm = 0
        self.spm_sum = 0
        self.spm_n = 0
        os.makedirs("data", exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.raw_path = os.path.join("data", f"frames_{stamp}.csv")
        self.raw_f = open(self.raw_path, "w", newline="")
        self.raw_w = csv.writer(self.raw_f)
        self.raw_w.writerow(["t", "hex", "len"] + [f"b{i}" for i in range(20)])
        self.steps_path = os.path.join("data", f"steps_{stamp}.csv")
        self.steps_f = open(self.steps_path, "w", newline="")
        self.steps_w = csv.writer(self.steps_f)
        self.steps_w.writerow(["t", "spm", "total_steps"])

    def close(self):
        self.raw_f.close()
        self.steps_f.close()

    def on_notify(self, _sender, data: bytearray):
        d = bytes(data)
        t = time.time() - self.start
        self.raw_w.writerow([f"{t:.3f}", d.hex(), len(d)] + list(d))
        self.frame_count += 1

        # Only F0 B2 frames carry live metrics.
        is_metrics = len(d) >= 14 and d[0] == 0xF0 and d[1] == 0xB2

        if self.raw:
            grid = " ".join(f"{i}:{b:02x}" for i, b in enumerate(d))
            tag = "B2" if is_metrics else "  "
            print(f"[{t:7.2f}s] {tag} ({len(d):2d}) {grid}")
            return

        if not is_metrics:
            return

        raw = d[SPM_BYTE] if len(d) > SPM_BYTE else 0
        self.spm = 0 if raw <= SPM_IDLE else raw

        # integrate cadence over real elapsed time to accumulate steps
        if self.last_t is not None:
            dt = t - self.last_t
            self.steps += self.spm * dt / 60.0
        self.last_t = t
        if self.spm:
            self.spm_sum += self.spm
            self.spm_n += 1

        avg = (self.spm_sum / self.spm_n) if self.spm_n else 0
        self.steps_w.writerow([f"{t:.3f}", self.spm, int(self.steps)])
        print(
            f"\rsteps: {int(self.steps):5d}   spm: {self.spm:3d}   "
            f"avg spm: {avg:4.1f}   time: {int(t):4d}s   frames {self.frame_count}",
            end="",
            flush=True,
        )


async def find_device(address: str | None):
    if address:
        print(f"Looking for {address} ...")
        dev = await BleakScanner.find_device_by_address(address, timeout=20.0)
        if dev:
            return dev
        print("Not found by address; falling back to a name scan.")
    print("Scanning 15s for an iConsole/stepper ...")
    devices = await BleakScanner.discover(timeout=15.0, return_adv=True)
    for dev, adv in devices.values():
        name = (dev.name or adv.local_name or "").lower()
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        if any(h in name for h in NAME_HINTS) or SVC_UUID in uuids:
            print(f"Match: {dev.name or adv.local_name} [{dev.address}]")
            return dev
    print("No obvious match. Devices seen:")
    for dev, adv in devices.values():
        print(f"  {dev.address}  {dev.name or adv.local_name or '?'}")
    return None


async def run(address: str | None, raw: bool, seconds: int):
    dev = await find_device(address)
    if not dev:
        print("No device. Power on the stepper, make sure it is not paired "
              "to the phone app, and retry (optionally pass --address).")
        return 1

    session = StepperSession(raw)
    print(f"Connecting to {dev.address} ...")
    try:
        async with BleakClient(dev) as client:
            print(f"Connected: {client.is_connected}")
            await asyncio.sleep(1.0)
            await client.start_notify(NOTIFY_UUID, session.on_notify)

            for frame in INIT_SEQUENCE:
                await client.write_gatt_char(WRITE_UUID, frame, response=False)
                await asyncio.sleep(0.25)
            print("Init sent. Step now. Ctrl-C to stop.\n")

            while True:
                await client.write_gatt_char(WRITE_UUID, POLL, response=False)
                await asyncio.sleep(POLL_INTERVAL)
                if seconds and (time.time() - session.start) >= seconds:
                    break

            await client.stop_notify(NOTIFY_UUID)
    except Exception as e:  # noqa: BLE001
        print(f"\nBLE error: {e}")
        return 2
    finally:
        session.close()
        print(f"\nRaw frames saved to {session.raw_path} "
              f"({session.frame_count} frames).")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Local iConsole+/DFX100 step counter")
    ap.add_argument("--address", help="BLE MAC address (skip scanning)")
    ap.add_argument("--raw", action="store_true",
                    help="calibration mode: print every frame byte-by-byte")
    ap.add_argument("--seconds", type=int, default=0,
                    help="stop after N seconds (0 = until Ctrl-C)")
    args = ap.parse_args()
    try:
        sys.exit(asyncio.run(run(args.address, args.raw, args.seconds)))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
