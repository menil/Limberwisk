"""In-memory `HidDevice` that replays recorded reports without sleeping."""

from collections import deque

from muteme_flow.hid_io import DeviceError


class FakeHidDevice:
    def __init__(self) -> None:
        self._queue: deque[list[int]] = deque()
        self._gone = False
        self._reads_until_unplug: int | None = None
        self.is_open = False
        self.opened_with: tuple[int, int] | None = None
        self.writes: list[bytes] = []

    def feed(self, *reports: list[int]) -> None:
        self._queue.extend(list(r) for r in reports)

    def disconnect(self) -> None:
        """Simulate an unplug: every later call raises DeviceError."""
        self._gone = True

    def disconnect_after(self, reads: int) -> None:
        """Unplug mid-stream, once `reads` more reads have been served."""
        self._reads_until_unplug = reads

    def open(self, vid: int, pid: int) -> None:
        if self._gone:
            raise DeviceError("device not connected")
        self.is_open = True
        self.opened_with = (vid, pid)

    def read(self, size: int, timeout_ms: int) -> list[int]:
        self._require_open()
        if self._reads_until_unplug is not None:
            if self._reads_until_unplug == 0:
                self._gone = True
                raise DeviceError("device not connected")
            self._reads_until_unplug -= 1
        # An empty queue stands in for a read timeout, so tests never block.
        return self._queue.popleft() if self._queue else []

    def write(self, data: bytes) -> int:
        self._require_open()
        self.writes.append(bytes(data))
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def _require_open(self) -> None:
        if self._gone:
            raise DeviceError("device not connected")
        if not self.is_open:
            raise DeviceError("device not open")
