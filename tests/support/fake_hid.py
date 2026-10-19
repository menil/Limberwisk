"""In-memory `HidDevice` that replays recorded reports without sleeping."""

import threading
import time
from collections import deque

from muteme_flow.devices import MUTEME_ORIGINAL_PID, MUTEME_VID
from muteme_flow.hid_io import DeviceError


class FakeHidDevice:
    def __init__(self, read_pause_s: float = 0.0) -> None:
        # Threaded tests set a tiny pause so an idle read does not spin the CPU.
        self._read_pause_s = read_pause_s
        self._queue: deque[list[int]] = deque()
        self._gone = False
        self._reads_until_unplug: int | None = None
        self.is_open = False
        self.opened_with: tuple[int, int] | None = None
        self.writes: list[bytes] = []
        # Idents of every thread that touched the device, to check the one-thread rule.
        self.call_threads: set[int] = set()

    @property
    def pending_reports(self) -> int:
        """Reports queued but not yet read; lets a test wait until the device is drained."""
        return len(self._queue)

    def feed(self, *reports: list[int]) -> None:
        self._queue.extend(list(r) for r in reports)

    def disconnect(self) -> None:
        """Simulate an unplug: every later call raises DeviceError."""
        self._gone = True

    def disconnect_after(self, reads: int) -> None:
        """Unplug mid-stream, once `reads` more reads have been served."""
        self._reads_until_unplug = reads

    def open(self, vid: int, pid: int) -> None:
        self._note_thread()
        if self._gone:
            raise DeviceError("device not connected")
        self.is_open = True
        self.opened_with = (vid, pid)

    def read(self, size: int, timeout_ms: int) -> list[int]:
        self._note_thread()
        self._require_open()
        if self._reads_until_unplug is not None:
            if self._reads_until_unplug == 0:
                self._gone = True
                raise DeviceError("device not connected")
            self._reads_until_unplug -= 1
        if self._queue:
            return self._queue.popleft()
        # An empty queue stands in for a read timeout.
        if self._read_pause_s:
            time.sleep(self._read_pause_s)
        return []

    def write(self, data: bytes) -> int:
        self._note_thread()
        self._require_open()
        self.writes.append(bytes(data))
        return len(data)

    def close(self) -> None:
        self._note_thread()
        self.is_open = False

    def _note_thread(self) -> None:
        self.call_threads.add(threading.get_ident())

    def _require_open(self) -> None:
        if self._gone:
            raise DeviceError("device not connected")
        if not self.is_open:
            raise DeviceError("device not open")


def opened(device: FakeHidDevice) -> FakeHidDevice:
    """Open `device` as a real connect callable would, and return it."""
    device.open(MUTEME_VID, MUTEME_ORIGINAL_PID)
    return device
