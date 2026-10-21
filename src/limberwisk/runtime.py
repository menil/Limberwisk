"""Assembles the real components and owns their start/stop order."""

import time
from collections.abc import Callable
from typing import Any, Protocol

from limberwisk.controller import Controller
from limberwisk.devices import DeviceId
from limberwisk.hid_worker import HidWorker
from limberwisk.protocols import FeedbackSink
from limberwisk.state_machine import Timings

# Longest wait at quit for the final stop command to be handed to the system.
SHUTDOWN_DRAIN_S = 0.5
_DRAIN_STEP_S = 0.01


class _Startable(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class ToggleableAudioSink(Protocol):
    enabled: bool


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
        audio_sink: ToggleableAudioSink | FeedbackSink | None = None,
        backend_factory: Callable[[str], tuple[Any, _Startable]] | None = None,
    ) -> None:
        self.controller = controller
        self._worker = worker
        self._presence = presence
        # Built last so it can be handed this runtime's own sleep/wake methods.
        self._power = make_power(self.sleep, self.wake)
        self._pump = pump
        self._audio_sink = audio_sink
        self._backend_factory = backend_factory
        self._stopped = False

    @property
    def connected_device_id(self) -> DeviceId | None:
        """Which known model is plugged in, for diagnostics."""
        return getattr(self._worker.connected_device, "device_id", None)

    @property
    def connected_device_name(self) -> str:
        """Human-readable model name of the plugged-in device, or default."""
        dev_id = self.connected_device_id
        if dev_id is not None:
            return getattr(dev_id, "model", str(dev_id))
        return "MuteMe"

    @property
    def backend_name(self) -> str:
        """Human-readable name of the active dictation backend."""
        return self.controller.backend_name

    def switch_backend(self, backend_choice: str) -> None:
        """Switch the active dictation backend, updating presence and halting active recording."""
        if self.controller.machine.recording:
            self.controller.machine.stop_recording()

        if self._presence is not None:
            self._presence.stop()

        if self._backend_factory is not None:
            backend, presence = self._backend_factory(backend_choice)
            self._presence = presence
        else:
            from limberwisk.envious_wispr_adapter import EnviousWisprBackend
            from limberwisk.main_thread import post_to_main
            from limberwisk.wispr_adapter import WisprFlowBackend
            from limberwisk.wispr_presence import WisprPresence

            backend = (
                EnviousWisprBackend.for_current_app(post_to_main)
                if backend_choice == "envious-wispr"
                else WisprFlowBackend.for_current_app(post_to_main)
            )
            self._presence = WisprPresence.for_current_app(
                self.controller.backend_running_changed,
                bundle_id=backend.bundle_id,
            )

        if not self._stopped and self._presence is not None:
            self._presence.start()

        # Update controller backend without triggering spurious false running state
        self.controller._backend = backend
        if self._presence is not None and hasattr(self._presence, "is_running"):
            self.controller.backend_running_changed(self._presence.is_running())

    def set_audio_feedback(self, enabled: bool) -> None:
        """Enable or disable audible feedback chimes."""
        if self._audio_sink is not None and hasattr(self._audio_sink, "enabled"):
            self._audio_sink.enabled = enabled

    @classmethod
    def create_default(
        cls,
        timings: Timings | None = None,
        backend_choice: str = "wispr-flow",
        audio_feedback: bool = False,
    ) -> "Runtime":
        """Build the real macOS runtime. Call on the main thread, before the run loop.

        Args:
            timings: Hold threshold and debounce timings for button interactions.
            backend_choice: Initial active dictation engine ('wispr-flow' or 'envious-wispr').
            audio_feedback: Whether audio chime feedback is initially enabled.
        """
        from limberwisk.envious_wispr_adapter import EnviousWisprBackend
        from limberwisk.feedback_sinks import AudioFeedbackSink, CompositeFeedbackSink
        from limberwisk.hidapi_device import open_first_known, preload_hidapi
        from limberwisk.led import LedMailbox
        from limberwisk.main_thread import post_to_main
        from limberwisk.muteme_adapter import MuteMeLedSink
        from limberwisk.power import PowerObserver
        from limberwisk.scheduler import NSTimerScheduler
        from limberwisk.wispr_adapter import WisprFlowBackend
        from limberwisk.wispr_presence import WisprPresence

        # hidapi must be imported on the main thread (specs/spec.md section 4.6).
        preload_hidapi()
        led = LedMailbox()
        led_sink = MuteMeLedSink(led)
        audio_sink = AudioFeedbackSink(enabled=audio_feedback)
        feedback = CompositeFeedbackSink([led_sink, audio_sink])

        backend = (
            EnviousWisprBackend.for_current_app(post_to_main)
            if backend_choice == "envious-wispr"
            else WisprFlowBackend.for_current_app(post_to_main)
        )

        controller = Controller(
            backend=backend,
            feedback=feedback,
            led=led,
            scheduler=NSTimerScheduler.for_current_app(),
            post_to_main=post_to_main,
            timings=timings,
        )
        presence = WisprPresence.for_current_app(
            controller.backend_running_changed,
            bundle_id=backend.bundle_id,
        )
        return cls(
            controller=controller,
            worker=HidWorker(open_first_known, led, controller.on_device_event),
            presence=presence,
            make_power=lambda on_sleep, on_wake: PowerObserver.for_current_app(on_sleep, on_wake),
            audio_sink=audio_sink,
        )

    def start(self) -> None:
        self._presence.start()
        self._power.start()
        self._worker.start()

    def stop(self) -> None:
        """Safe to call more than once: quit paths (menu, signal, terminate) can overlap."""
        if self._stopped:
            return
        self._stopped = True
        # Stop Wispr and queue the red LED first: nothing else matters if it does not happen.
        self.controller.shutdown()
        try:
            self._power.stop()
            self._presence.stop()
            self._drain()
        finally:
            # The worker writes the final LED colour as it exits, so it must always run.
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
