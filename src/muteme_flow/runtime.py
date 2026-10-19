"""Assembles the real components and owns their start/stop order."""

import time
from collections.abc import Callable
from typing import Protocol

from muteme_flow.controller import Controller
from muteme_flow.hid_worker import HidWorker

# Longest wait at quit for the final stop command to be handed to the system.
SHUTDOWN_DRAIN_S = 0.5
_DRAIN_STEP_S = 0.01


class _Startable(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


def pump_run_loop(seconds: float) -> None:
    """Let the main run loop run for `seconds`, sleeping if it has nothing to service.

    `runUntilDate_` returns at once when no sources or timers are installed, which is
    exactly the state during shutdown, so the remainder is slept off explicitly.
    """
    from Foundation import NSDate, NSRunLoop

    started = time.monotonic()
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    remaining = seconds - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)


class Runtime:
    def __init__(
        self,
        *,
        controller: Controller,
        worker: HidWorker,
        presence: _Startable,
        make_power: Callable[[Callable[[], None], Callable[[], None]], _Startable],
        pump: Callable[[float], None] = pump_run_loop,
    ) -> None:
        self.controller = controller
        self._worker = worker
        self._presence = presence
        # Built last so it can be handed this runtime's own sleep/wake methods.
        self._power = make_power(self.sleep, self.wake)
        self._pump = pump

    @classmethod
    def create_default(cls) -> "Runtime":
        """Build the real macOS runtime. Call on the main thread, before the run loop."""
        from muteme_flow.dispatcher import NSWorkspaceDispatcher
        from muteme_flow.hidapi_device import open_first_known, preload_hidapi
        from muteme_flow.led import LedMailbox
        from muteme_flow.main_thread import post_to_main
        from muteme_flow.power import PowerObserver
        from muteme_flow.scheduler import NSTimerScheduler
        from muteme_flow.wispr_presence import WisprPresence

        # hidapi must be imported on the main thread (specs/spec.md section 4.6).
        preload_hidapi()
        led = LedMailbox()
        controller = Controller(
            dispatcher=NSWorkspaceDispatcher.for_current_app(post_to_main),
            led=led,
            scheduler=NSTimerScheduler.for_current_app(),
            post_to_main=post_to_main,
        )
        return cls(
            controller=controller,
            worker=HidWorker(open_first_known, led, controller.on_device_event),
            presence=WisprPresence.for_current_app(controller.wispr_running_changed),
            make_power=lambda on_sleep, on_wake: PowerObserver.for_current_app(on_sleep, on_wake),
        )

    def start(self) -> None:
        self._presence.start()
        self._power.start()
        self._worker.start()

    def stop(self) -> None:
        self._power.stop()
        self._presence.stop()
        # Queue the final stop and red LED first; the worker writes the LED as it exits.
        self.controller.shutdown()
        self._drain()
        self._worker.stop()

    def sleep(self) -> None:
        self._worker.pause()

    def wake(self) -> None:
        # Reconnect first, then resync Wispr (specs/spec.md section 4.5).
        self._worker.resume()
        self.controller.wake()

    def _drain(self) -> None:
        deadline = time.monotonic() + SHUTDOWN_DRAIN_S
        while self.controller.outstanding_dispatches > 0 and time.monotonic() < deadline:
            self._pump(_DRAIN_STEP_S)
