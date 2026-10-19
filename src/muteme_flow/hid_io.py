"""The seam between the app and a USB HID device.

Everything above this layer talks to `HidDevice`, so the real hidapi-backed device
and the test fake are interchangeable (specs/spec.md section 8.1).
"""

from typing import Protocol, runtime_checkable


class DeviceError(Exception):
    """The device is gone or an I/O call failed."""


# runtime_checkable lets tests assert the fake and the real adapter both satisfy it.
@runtime_checkable
class HidDevice(Protocol):
    def open(self, vid: int, pid: int) -> None:
        """Open the first device matching (vid, pid). Raises DeviceError on failure."""

    def read(self, size: int, timeout_ms: int) -> list[int]:
        """Block up to timeout_ms for a report.

        Returns [] on timeout and raises DeviceError if the device is gone.
        """

    def write(self, data: bytes) -> int:
        """Send an output report (first byte is the report ID). Returns bytes written."""

    def close(self) -> None:
        """Release the device. Safe to call more than once."""
