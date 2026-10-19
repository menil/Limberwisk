"""Measures how long a device event takes to become a dispatched command.

The 25 ms touch-to-dispatch goal (specs/spec.md section 8) is only checkable if the
real app records it, including the hop from the HID thread to the main thread.
"""

import statistics
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencySummary:
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


class LatencyRecorder:
    def __init__(self, clock: Callable[[], float], capacity: int = 1000) -> None:
        self._clock = clock
        self._received_at: float | None = None
        self._samples_ms: deque[float] = deque(maxlen=capacity)

    def now(self) -> float:
        return self._clock()

    def input_received(self, at: float) -> None:
        """Mark when the HID thread decoded the edge now being processed."""
        self._received_at = at

    def dispatched(self) -> None:
        """Call once the command has been handed to the system, so the time spent
        building and submitting it counts toward the figure."""
        if self._received_at is not None:
            self._samples_ms.append((self._clock() - self._received_at) * 1000)

    def clear_input(self) -> None:
        self._received_at = None

    @property
    def samples_ms(self) -> list[float]:
        return list(self._samples_ms)

    def summary(self) -> LatencySummary | None:
        if not self._samples_ms:
            return None
        ordered = sorted(self._samples_ms)
        return LatencySummary(
            count=len(ordered),
            p50_ms=statistics.median(ordered),
            p95_ms=ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
            max_ms=ordered[-1],
        )
