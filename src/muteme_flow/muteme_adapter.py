"""Adapter exposing MuteMe USB buttons via the InputSource and FeedbackSink protocols."""

import time
from collections.abc import Callable

from muteme_flow.hid_io import HidDevice
from muteme_flow.hid_worker import RECONNECT_INTERVAL_S, DeviceEvent, HidWorker
from muteme_flow.led import Color, LedMailbox
from muteme_flow.protocols import (
    FeedbackSink,
    FeedbackState,
    InputEventHandler,
    InputSource,
    device_event_to_input_event,
    feedback_state_to_color,
)


class MuteMeLedSink(FeedbackSink):
    """Feedback sink adapter controlling a MuteMe button's LED."""

    def __init__(self, mailbox: LedMailbox) -> None:
        self._mailbox = mailbox

    @property
    def mailbox(self) -> LedMailbox:
        return self._mailbox

    def set_state(self, state: FeedbackState | Color) -> None:
        """Update the active feedback state.

        Accepts either a generic `FeedbackState` or a hardware-specific `Color`.
        Generic consumers should prefer `FeedbackState`.
        """
        if isinstance(state, FeedbackState):
            self._mailbox.request(feedback_state_to_color(state))
        elif isinstance(state, Color):
            self._mailbox.request(state)
        else:
            raise ValueError(f"Expected FeedbackState or Color, got: {state!r}")

    def mark_for_resend(self) -> None:
        self._mailbox.mark_for_resend()


class MuteMeInputSource(InputSource):
    """Input source adapter for MuteMe USB hardware buttons."""

    def __init__(
        self,
        connect: Callable[[], HidDevice],
        led_mailbox: LedMailbox,
        *,
        clock: Callable[[], float] = time.monotonic,
        reconnect_interval_s: float = RECONNECT_INTERVAL_S,
    ) -> None:
        self._connect = connect
        self._led_mailbox = led_mailbox
        self._clock = clock
        self._reconnect_interval_s = reconnect_interval_s
        self._worker: HidWorker | None = None
        self._on_event: InputEventHandler | None = None

    @property
    def name(self) -> str:
        return "MuteMe"

    @property
    def connected_device(self) -> HidDevice | None:
        return self._worker.connected_device if self._worker else None

    @property
    def worker(self) -> HidWorker | None:
        return self._worker

    def start(self, on_event: InputEventHandler) -> None:
        self._on_event = on_event

        def _handle_device_event(event: DeviceEvent) -> None:
            if self._on_event:
                self._on_event(device_event_to_input_event(event))

        self._worker = HidWorker(
            self._connect,
            self._led_mailbox,
            _handle_device_event,
            clock=self._clock,
            reconnect_interval_s=self._reconnect_interval_s,
        )
        self._worker.start()

    def stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None

    def pause(self) -> None:
        if self._worker:
            self._worker.pause()

    def resume(self) -> None:
        if self._worker:
            self._worker.resume()
