"""LED colours and a thread-safe mailbox for requesting them (spec section 3.2)."""

import threading
from enum import IntEnum


class Color(IntEnum):
    OFF = 0x00
    RED = 0x01
    GREEN = 0x02
    YELLOW = 0x03
    BLUE = 0x04


REPORT_ID = 0x00


def led_report(color: Color) -> bytes:
    """The exact 2-byte output report: the report ID then one colour byte.

    The spec forbids relying on padding, so this is the only shape ever sent.
    """
    return bytes([REPORT_ID, color])


class LedMailbox:
    """Hand-off between the thread requesting a colour and the HID thread writing it.

    hidapi device handles are not safe to use from two threads, so only the HID thread
    writes. Requests coalesce: if several arrive before the next write, only the latest
    colour matters.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wanted: Color | None = None
        self._dirty = False

    def request(self, color: Color) -> None:
        with self._lock:
            self._wanted = color
            self._dirty = True

    def set_state(self, state: object) -> None:
        """Conform to FeedbackSink by accepting a FeedbackState or Color.

        FeedbackState is the preferred semantic representation for decoupled
        feedback sinks. Color is supported for direct/legacy callers.
        """
        from muteme_flow.protocols import FeedbackState, feedback_state_to_color

        if isinstance(state, FeedbackState):
            self.request(feedback_state_to_color(state))
        elif isinstance(state, Color):
            self.request(state)
        else:
            raise ValueError(f"Expected FeedbackState or Color, got: {state!r}")

    def mark_for_resend(self) -> None:
        """Re-queue the last colour, for a freshly (re)connected device that lost it."""
        with self._lock:
            self._dirty = self._wanted is not None

    def take_pending(self) -> Color | None:
        with self._lock:
            if not self._dirty:
                return None
            self._dirty = False
            return self._wanted
