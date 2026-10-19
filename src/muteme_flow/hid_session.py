"""One connected session with a device: LED writes in, touch edges out."""

import time
from collections.abc import Callable

from muteme_flow.decoder import Edge, EdgeDecoder
from muteme_flow.hid_io import DeviceError, HidDevice
from muteme_flow.led import LedMailbox, led_report

REPORT_BUFFER_SIZE = 64
# Short so a requested LED colour reaches the device promptly even while untouched, when
# the device only sends a heartbeat every ~0.5 s. The wake-ups are cheap.
READ_TIMEOUT_MS = 50
# The device sends a report at least every ~0.5 s, so silence this long means it is gone
# even if the OS has not reported an error.
WATCHDOG_S = 1.5


class HidSession:
    """Drives one connected device. Single-threaded: call `step` from the HID thread only."""

    def __init__(
        self,
        device: HidDevice,
        led: LedMailbox,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._device = device
        self._led = led
        self._clock = clock
        self._decoder = EdgeDecoder()
        self._last_report_at = clock()

    def step(self) -> Edge | None:
        """Apply a pending LED change, then wait for one report. Raises DeviceError."""
        self.flush_led()

        report = self._device.read(REPORT_BUFFER_SIZE, READ_TIMEOUT_MS)
        now = self._clock()
        if not report:
            if now - self._last_report_at > WATCHDOG_S:
                raise DeviceError("no reports from the device (watchdog)")
            return None

        self._last_report_at = now
        return self._decoder.feed(report)

    def flush_led(self) -> None:
        """Write the requested colour, if any. Also used for a last write before closing."""
        pending = self._led.take_pending()
        if pending is not None:
            self._device.write(led_report(pending))
