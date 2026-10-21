"""Time and one-shot timers, behind an interface so logic can be tested with a fake clock."""

import time
from collections.abc import Callable
from typing import Any, Protocol

from limberwisk.guarded import guarded


class TimerHandle(Protocol):
    def cancel(self) -> None: ...


class Scheduler(Protocol):
    def now(self) -> float:
        """Monotonic seconds."""

    def call_later(self, delay_s: float, fn: Callable[[], None]) -> TimerHandle:
        """Run `fn` once, on the main thread, after `delay_s`."""


class _NSTimerHandle:
    def __init__(self, timer: Any) -> None:
        self._timer = timer

    def cancel(self) -> None:
        self._timer.invalidate()


class NSTimerScheduler:
    """Main-run-loop timers. Must be used from the main thread (specs/spec.md section 4.6)."""

    def __init__(self, *, timer_class: Any, run_loop: Any, common_modes: Any) -> None:
        self._timer_class = timer_class
        self._run_loop = run_loop
        self._common_modes = common_modes

    @classmethod
    def for_current_app(cls) -> "NSTimerScheduler":
        # Imported here so the module loads where Foundation is unavailable (Linux CI).
        from Foundation import NSRunLoop, NSRunLoopCommonModes, NSTimer

        return cls(
            timer_class=NSTimer, run_loop=NSRunLoop.mainRunLoop(), common_modes=NSRunLoopCommonModes
        )

    def now(self) -> float:
        return time.monotonic()

    def call_later(self, delay_s: float, fn: Callable[[], None]) -> TimerHandle:
        callback = guarded(fn, "timer callback")
        timer = self._timer_class.timerWithTimeInterval_repeats_block_(
            delay_s, False, lambda _timer: callback()
        )
        # Common modes, not the default one, so timers still fire while a menu is open.
        self._run_loop.addTimer_forMode_(timer, self._common_modes)
        return _NSTimerHandle(timer)
