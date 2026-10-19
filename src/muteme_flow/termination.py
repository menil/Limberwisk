"""Turns SIGTERM/SIGINT into an orderly quit (specs/spec.md section 4.5)."""

import signal
from collections.abc import Callable
from typing import Any

# A Cocoa run loop never returns control to the interpreter on its own, so Python-level
# signal handlers would not run. A cheap repeating timer wakes it to check.
_WAKE_INTERVAL_S = 0.5


def install_termination_handlers(
    on_terminate: Callable[[], None],
    post_to_main: Callable[[Callable[[], None]], None],
    *,
    signal_module: Any = signal,
) -> None:
    def handler(signum: int, _frame: Any) -> None:
        # Restore the default so a second signal still ends a hung app.
        signal_module.signal(signum, signal.SIG_DFL)
        post_to_main(on_terminate)

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal_module.signal(signum, handler)


def keep_interpreter_responsive() -> None:
    """Start the wake-up timer. Main thread, after the run loop exists."""
    from Foundation import NSRunLoop, NSRunLoopCommonModes, NSTimer

    timer = NSTimer.timerWithTimeInterval_repeats_block_(_WAKE_INTERVAL_S, True, lambda _t: None)
    NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
