"""Raw BLE frame and step CSV logs, same columns as the root stepper.py."""

import csv
import os
import threading
from datetime import datetime
from pathlib import Path

FRAME_HEADER = ["t", "hex", "len"] + [f"b{i}" for i in range(20)]
STEP_HEADER = ["t", "spm", "total_steps"]


class FrameLog:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = threading.Lock()
        self._closed = False
        self._frames_f = None
        self._steps_f = None
        self._frames_w = None
        self._steps_w = None

    @staticmethod
    def default_dir() -> Path:
        home = os.environ.get("STEPPER_QUESTS_HOME")
        base = Path(home) if home else Path.home() / ".local/share/stepper-quests"
        return base / "data"

    def open_session(self) -> None:
        with self._lock:
            self._closed = False
            self._open_locked()

    def _open_locked(self) -> None:
        if self._frames_f is not None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Line buffered so a crash or power cut loses at most one row.
        self._frames_f = open(self.directory / f"frames_{stamp}.csv", "w",
                              newline="", buffering=1)
        self._steps_f = open(self.directory / f"steps_{stamp}.csv", "w",
                             newline="", buffering=1)
        self._frames_w = csv.writer(self._frames_f)
        self._steps_w = csv.writer(self._steps_f)
        self._frames_w.writerow(FRAME_HEADER)
        self._steps_w.writerow(STEP_HEADER)

    def write_frame(self, t: float, data: bytes) -> None:
        with self._lock:
            if self._closed:
                return
            self._open_locked()
            self._frames_w.writerow([f"{t:.3f}", data.hex(), len(data)] + list(data))

    def write_step(self, t: float, spm: int, total_steps: int) -> None:
        with self._lock:
            if self._closed:
                return
            self._open_locked()
            self._steps_w.writerow([f"{t:.3f}", spm, int(total_steps)])

    def close(self) -> None:
        """Close the files; later writes are dropped until open_session()."""
        with self._lock:
            self._closed = True
            for f in (self._frames_f, self._steps_f):
                if f is not None:
                    f.close()
            self._frames_f = self._steps_f = None
            self._frames_w = self._steps_w = None
