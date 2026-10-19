"""Turns raw MuteMe input reports into touch edges (specs/spec.md section 3.2).

Only data[3] carries information: 0x04 touch begins, 0x01 touch held, 0x02 touch ends,
0x00 idle. 0x00 is also the idle heartbeat, so it is never a release on its own; the
decoder is driven by transitions, not levels.
"""

from collections.abc import Sequence
from enum import Enum, auto

STATE_INDEX = 3
TOUCH_BEGIN = 0x04
TOUCH_HELD = 0x01
TOUCH_END = 0x02
IDLE = 0x00


class Edge(Enum):
    DOWN = auto()
    UP = auto()


class _State(Enum):
    READY = auto()  # untouched, waiting for a fresh touch-begin
    TOUCHING = auto()
    # The device was already being touched when we started listening, so the
    # touch-begin was missed. Ignore the rest of that touch (spec section 4.5).
    STALE_TOUCH = auto()


class EdgeDecoder:
    def __init__(self) -> None:
        self._state = _State.READY

    def feed(self, report: Sequence[int]) -> Edge | None:
        if len(report) <= STATE_INDEX:
            return None
        code = report[STATE_INDEX]

        if self._state is _State.READY:
            if code == TOUCH_BEGIN:
                self._state = _State.TOUCHING
                return Edge.DOWN
            if code == TOUCH_HELD:
                self._state = _State.STALE_TOUCH
            return None

        if self._state is _State.STALE_TOUCH:
            if code in (IDLE, TOUCH_END):
                self._state = _State.READY
            elif code == TOUCH_BEGIN:
                self._state = _State.TOUCHING
                return Edge.DOWN
            return None

        # TOUCHING. A zero without a preceding touch-end still releases, in case the
        # device or the OS drops the end report.
        if code in (TOUCH_END, IDLE):
            self._state = _State.READY
            return Edge.UP
        return None
