"""Connects device events to the state machine and the state machine to Wispr Flow.

The one thread-crossing point in the app: `on_device_event` is called on the HID thread
and hands everything to the main thread, where the state machine lives
(specs/spec.md section 4.6).
"""

import logging
from collections.abc import Callable

from muteme_flow.commands import Command
from muteme_flow.dispatcher import Completion, DispatchError, UrlDispatcher
from muteme_flow.hid_worker import DeviceEvent
from muteme_flow.latency import LatencyRecorder
from muteme_flow.led import LedMailbox
from muteme_flow.scheduler import Scheduler
from muteme_flow.state_machine import StateMachine, Timings

log = logging.getLogger(__name__)


class Controller:
    def __init__(
        self,
        *,
        dispatcher: UrlDispatcher,
        led: LedMailbox,
        scheduler: Scheduler,
        post_to_main: Callable[[Callable[[], None]], None],
        timings: Timings | None = None,
        latency: LatencyRecorder | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._post_to_main = post_to_main
        # One clock for timestamps taken on the HID thread and for gesture timing on the
        # main thread, so the two can be compared.
        self._now = scheduler.now
        self.latency = latency or LatencyRecorder(self._now)
        # The UI sets this to refresh itself when anything it shows may have changed.
        self.on_change: Callable[[], None] = lambda: None
        self._refresh_pending = False
        self.machine = StateMachine(
            send=self._send,
            set_led=led.request,
            scheduler=scheduler,
            timings=timings,
            on_change=self._schedule_refresh,
        )
        self._handlers: dict[DeviceEvent, Callable[[float], None]] = {
            DeviceEvent.DOWN: lambda at: self.machine.touch_down(at),
            DeviceEvent.UP: lambda at: self.machine.touch_up(at),
            DeviceEvent.CONNECTED: lambda _at: self.machine.device_attached(),
            DeviceEvent.DISCONNECTED: lambda _at: self.machine.device_detached(),
            DeviceEvent.OPEN_FAILED: lambda _at: self.machine.device_open_failed(),
        }
        self._outstanding = 0

    @property
    def outstanding_dispatches(self) -> int:
        """Commands handed to the system whose completion has not arrived yet."""
        return self._outstanding

    def on_device_event(self, event: DeviceEvent) -> None:
        """HID thread. Must return quickly: it only timestamps and posts."""
        received_at = self._now()
        self._post_to_main(lambda: self._handle(event, received_at))

    def wispr_running_changed(self, running: bool) -> None:
        self.machine.wispr_running_changed(running)

    def conflict_changed(self, conflict: bool) -> None:
        self.machine.set_conflict(conflict)

    def wake(self) -> None:
        self.machine.wake()

    def shutdown(self) -> None:
        self.machine.shutdown()

    def _schedule_refresh(self) -> None:
        """Defer the UI update until after the current transition, and merge bursts.

        A menu refresh is slow next to the work around a touch, and a bug in it must not
        abort a state change, so it never runs inline.
        """
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._post_to_main(self._refresh)

    def _refresh(self) -> None:
        self._refresh_pending = False
        try:
            self.on_change()
        except Exception:
            log.exception("error while refreshing the menu")

    def _handle(self, event: DeviceEvent, received_at: float) -> None:
        self.latency.input_received(received_at)
        try:
            self._handlers[event](received_at)
        except Exception:
            log.exception("error while handling %s", event)
        finally:
            self.latency.clear_input()

    def _send(self, command: Command, on_complete: Completion) -> None:
        self._outstanding += 1

        def completed(error: Exception | None) -> None:
            self._outstanding -= 1
            on_complete(error)

        try:
            self._dispatcher.dispatch(command, completed)
        except Exception as error:
            # A dispatcher that raises must still end in the failure path, or the state
            # machine would believe a command is in flight forever. Posted rather than
            # called, so the machine is not re-entered mid-transition.
            failure = DispatchError(f"{type(error).__name__}: {error}")
            self._post_to_main(lambda: completed(failure))
        self.latency.dispatched()
