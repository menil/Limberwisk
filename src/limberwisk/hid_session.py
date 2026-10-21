"""One connected session with a device: LED writes in, touch edges out."""

import time
from collections.abc import Callable

from limberwisk.decoder import Edge, EdgeDecoder
from limberwisk.hid_io import DeviceError, HidDevice
from limberwisk.led import LedMailbox, led_report

REPORT_BUFFER_SIZE = 64
# How long a read waits when the device is silent. It bounds how late an LED change can be
# written when nothing is happening, and how soon the worker notices stop/pause. Idle CPU
# is the reason it is long: 50 ms (20 wake-ups a second) measured 0.27% of a core, 250 ms
# 0.10% (specs/spec.md section 10.1).
IDLE_READ_TIMEOUT_MS = 250
# While a touch is in progress, and for a moment after, wake often: the LED changes that
# follow a touch (for example back to red on release) must reach the device promptly.
BUSY_READ_TIMEOUT_MS = 40
BUSY_WINDOW_S = 1.0
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
        self._short_reads_until = 0.0

    def step(self) -> Edge | None:
        """Apply a pending LED change, then wait for one report. Raises DeviceError."""
        self.flush_led()

        busy = self._clock() < self._short_reads_until
        timeout_ms = BUSY_READ_TIMEOUT_MS if busy else IDLE_READ_TIMEOUT_MS
        report = self._device.read(REPORT_BUFFER_SIZE, timeout_ms)
        now = self._clock()
        if not report:
            if now - self._last_report_at > WATCHDOG_S:
                raise DeviceError("no reports from the device (watchdog)")
            return None

        self._last_report_at = now
        edge = self._decoder.feed(report)
        if edge is not None:
            self._short_reads_until = now + BUSY_WINDOW_S
        return edge

    def flush_led(self) -> None:
        """Write the requested colour, if any. Also used for a last write before closing."""
        pending = self._led.take_pending()
        if pending is not None:
            self._device.write(led_report(pending))
