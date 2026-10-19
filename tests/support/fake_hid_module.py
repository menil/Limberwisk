"""Stand-in for the `hid` module, so the hidapi adapter is testable without hardware."""

from typing import Any


class FakeRawDevice:
    """Mimics `hid.device`, including its habit of raising OSError on I/O failure."""

    def __init__(self, reports: list[list[int]] | None = None) -> None:
        self.reports = list(reports or [])
        self.opened_with: tuple[int, int] | None = None
        self.nonblocking: int | None = None
        self.written: list[bytes] = []
        self.closed = False
        self.open_error: Exception | None = None
        self.read_error: Exception | None = None
        self.write_error: Exception | None = None
        self.write_result: int | None = None
        self.close_error: Exception | None = None

    def open(self, vid: int, pid: int) -> None:
        if self.open_error:
            raise self.open_error
        self.opened_with = (vid, pid)

    def set_nonblocking(self, value: int) -> None:
        self.nonblocking = value

    def read(self, size: int, timeout_ms: int) -> list[int]:
        if self.read_error:
            raise self.read_error
        return self.reports.pop(0) if self.reports else []

    def write(self, data: bytes) -> int:
        if self.write_error:
            raise self.write_error
        self.written.append(bytes(data))
        return self.write_result if self.write_result is not None else len(data)

    def close(self) -> None:
        self.closed = True
        if self.close_error:
            raise self.close_error


class FakeHidModule:
    def __init__(self, listing: list[dict[str, Any]] | None = None) -> None:
        self.listing = listing or []
        self.created: list[FakeRawDevice] = []
        self.next_device_factory = FakeRawDevice

    def enumerate(self, vid: int = 0, pid: int = 0) -> list[dict[str, Any]]:
        # Like hidapi, a zero means "any".
        return [
            entry
            for entry in self.listing
            if vid in (0, entry["vendor_id"]) and pid in (0, entry["product_id"])
        ]

    def device(self) -> FakeRawDevice:
        raw = self.next_device_factory()
        self.created.append(raw)
        return raw
