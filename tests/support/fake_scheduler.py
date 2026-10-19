"""Manually advanced `Scheduler`: timers fire only when the test moves time forward."""

import heapq
import itertools
from collections.abc import Callable


class FakeTimer:
    def __init__(self) -> None:
        self.cancelled = False
        self.fired = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeScheduler:
    def __init__(self, start: float = 1000.0) -> None:
        self._now = start
        self._queue: list[tuple[float, int, FakeTimer, Callable[[], None]]] = []
        self._order = itertools.count()
        self.timers: list[FakeTimer] = []

    def now(self) -> float:
        return self._now

    def call_later(self, delay_s: float, fn: Callable[[], None]) -> FakeTimer:
        timer = FakeTimer()
        self.timers.append(timer)
        heapq.heappush(self._queue, (self._now + delay_s, next(self._order), timer, fn))
        return timer

    def advance(self, seconds: float) -> None:
        """Move time forward, firing due timers in order at their own due times."""
        target = self._now + seconds
        while self._queue and self._queue[0][0] <= target:
            due, _, timer, fn = heapq.heappop(self._queue)
            if timer.cancelled:
                continue
            self._now = due
            timer.fired = True
            fn()
        self._now = target

    @property
    def pending(self) -> int:
        return sum(1 for _, _, timer, _ in self._queue if not timer.cancelled)
