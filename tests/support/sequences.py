"""Input reports recorded from a real MuteMe Original (0x3603:0x0001).

Only data[3] carries information (specs/spec.md section 3.2):
0x04 touch begins, 0x01 touch held (~70 Hz), 0x02 touch ends, 0x00 idle.
The default counts below approximate what was recorded: a quick tap lasted 123 ms
and a deliberate hold 1.465 s, with held reports arriving about every 14 ms.
"""

REPORT_SIZE = 8

TOUCH_BEGIN = 0x04
TOUCH_HELD = 0x01
TOUCH_END = 0x02
IDLE = 0x00


def report(value: int) -> list[int]:
    return [0, 0, 0, value, 0, 0, 0, 0]


def idle(count: int = 1) -> list[list[int]]:
    """Heartbeat reports the device emits roughly every 0.5 s while untouched."""
    return [report(IDLE) for _ in range(count)]


def touch(held_reports: int) -> list[list[int]]:
    """One complete touch: begin, N held reports, end, then the return to idle."""
    return [
        report(TOUCH_BEGIN),
        *[report(TOUCH_HELD) for _ in range(held_reports)],
        report(TOUCH_END),
        report(IDLE),
    ]


def tap() -> list[list[int]]:
    """A quick tap (about 120 ms, seven held reports)."""
    return touch(held_reports=7)


def hold(held_reports: int = 100) -> list[list[int]]:
    """A deliberate hold (about 1.4 s at ~70 Hz)."""
    return touch(held_reports=held_reports)
