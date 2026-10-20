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
from muteme_flow.led import Color, LedMailbox
from muteme_flow.protocols import (
    DictationBackend,
    FeedbackSink,
    FeedbackState,
    InputEvent,
    color_to_feedback_state,
    command_to_dictation_command,
    feedback_state_to_color,
    input_event_to_device_event,
)
from muteme_flow.scheduler import Scheduler
from muteme_flow.settings import BACKEND_DISPLAY_NAMES, DEFAULT_BACKEND
from muteme_flow.state_machine import StateMachine, Timings

log = logging.getLogger(__name__)


class Controller:
    def __init__(
        self,
        *,
        backend: DictationBackend | None = None,
        dispatcher: UrlDispatcher | None = None,
        feedback: FeedbackSink | None = None,
        led: LedMailbox | None = None,
        scheduler: Scheduler,
        post_to_main: Callable[[Callable[[], None]], None],
        timings: Timings | None = None,
        latency: LatencyRecorder | None = None,
    ) -> None:
        if backend is None and dispatcher is None:
            raise ValueError("Either backend or dispatcher must be provided")
        if feedback is None and led is None:
            raise ValueError("Either feedback or led must be provided")

        self._backend = backend
        self._dispatcher = dispatcher
        self._feedback = feedback
        self._led = led
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
            set_led=self._set_feedback,
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

    @property
    def backend(self) -> DictationBackend | None:
        """Active dictation backend."""
        return self._backend

    @property
    def backend_name(self) -> str:
        """Active backend display name, or fallback if unset."""
        if self._backend is not None and hasattr(self._backend, "name"):
            return str(self._backend.name)
        return BACKEND_DISPLAY_NAMES.get(DEFAULT_BACKEND, "Wispr Flow")

    def set_backend(self, backend: DictationBackend) -> None:
        """Switch the active dictation backend and synchronize running state."""
        self._backend = backend
        self.backend_running_changed(backend.is_running())

    def _set_feedback(self, color_or_state: Color | FeedbackState) -> None:
        if self._feedback is not None:
            state = (
                color_or_state
                if isinstance(color_or_state, FeedbackState)
                else color_to_feedback_state(color_or_state)
            )
            self._feedback.set_state(state)
        elif self._led is not None:
            color = (
                color_or_state
                if isinstance(color_or_state, Color)
                else feedback_state_to_color(color_or_state)
            )
            self._led.request(color)

    def on_device_event(self, event: DeviceEvent | InputEvent) -> None:
        """Input thread. Must return quickly: it only timestamps and posts."""
        dev_event = input_event_to_device_event(event) if isinstance(event, InputEvent) else event
        received_at = self._now()
        self._post_to_main(lambda: self._handle(dev_event, received_at))

    def backend_running_changed(self, running: bool) -> None:
        self.machine.wispr_running_changed(running)

    def wispr_running_changed(self, running: bool) -> None:
        self.backend_running_changed(running)

    def conflict_changed(self, conflict: bool) -> None:
        self.machine.set_conflict(conflict)

    def wake(self) -> None:
        self.machine.wake()

    def shutdown(self) -> None:
        self.machine.shutdown()

    def schedule_refresh(self) -> None:
        """Coalesce rapid events into a single UI refresh on the next run loop pass."""
        self._schedule_refresh()

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
            if self._backend is not None:
                self._backend.dispatch(command_to_dictation_command(command), completed)
            elif self._dispatcher is not None:
                self._dispatcher.dispatch(command, completed)
        except Exception as error:
            # A dispatcher that raises must still end in the failure path, or the state
            # machine would believe a command is in flight forever. Posted rather than
            # called, so the machine is not re-entered mid-transition.
            failure = DispatchError(f"{type(error).__name__}: {error}")
            self._post_to_main(lambda: completed(failure))
        self.latency.dispatched()
