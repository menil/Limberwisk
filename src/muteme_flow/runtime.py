"""Assembles the real components and owns their start/stop order."""

import time
from collections.abc import Callable
from typing import Any, Protocol

from muteme_flow.controller import Controller
from muteme_flow.devices import DeviceId
from muteme_flow.hid_worker import HidWorker
from muteme_flow.protocols import FeedbackSink, InputSource
from muteme_flow.state_machine import Timings

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
        worker: HidWorker | None = None,
        input_source: InputSource | None = None,
        presence: _Startable,
        make_power: Callable[[Callable[[], None], Callable[[], None]], _Startable],
        pump: Callable[[float], None] = pump_run_loop,
        audio_sink: ToggleableAudioSink | FeedbackSink | None = None,
        backend_factory: Callable[[str], tuple[Any, _Startable]] | None = None,
        input_factory: Callable[[str], InputSource] | None = None,
        conflict_monitor: Any = None,
        led_mailbox: Any = None,
    ) -> None:
        """Initialize the runtime with core services and active input/backend sources.

        Args:
            controller: Central coordinator for state machine and hardware events.
            worker: Deprecated raw HID worker fallback (prefer input_source).
            input_source: Active InputSource instance. May optionally expose a `worker` attribute
                for diagnostic device identification.
            presence: Application presence tracker for the dictation backend.
            make_power: Factory for system power state observers.
            pump: Run loop pump function.
            audio_sink: Optional audio chime feedback sink.
            backend_factory: Factory for resolving dictation backends.
            input_factory: Factory for resolving input sources by choice key.
            conflict_monitor: Optional ConflictMonitor instance to synchronize targets with.
            led_mailbox: Optional LedMailbox reference for input source factory creation.
        """
        self.controller = controller
        self._input_source = input_source
        self._worker = worker if worker is not None else getattr(input_source, "worker", None)
        self._presence = presence
        # Built last so it can be handed this runtime's own sleep/wake methods.
        self._power = make_power(self.sleep, self.wake)
        self._pump = pump
        self._audio_sink = audio_sink
        self._backend_factory = backend_factory
        self._input_factory = input_factory
        self._led_mailbox = led_mailbox
        self._conflict_monitor: Any = None
        self._stopped = False
        # Use property setter to synchronize initial conflicts with monitor
        self.conflict_monitor = conflict_monitor

    @property
    def conflict_monitor(self) -> Any:
        """The active ConflictMonitor instance, if configured."""
        return self._conflict_monitor

    @conflict_monitor.setter
    def conflict_monitor(self, monitor: Any) -> None:
        """Assign conflict monitor and immediately synchronize target conflicting apps."""
        self._conflict_monitor = monitor
        self._update_conflict_monitor(self._input_source)

    def _update_conflict_monitor(self, input_source: Any) -> None:
        """Synchronize the conflict monitor with an input source's declared conflicts."""
        if (
            self._conflict_monitor is not None
            and hasattr(self._conflict_monitor, "set_conflicts")
            and input_source is not None
        ):
            bundle_ids = getattr(input_source, "conflicting_bundle_ids", frozenset())
            app_names = getattr(input_source, "conflicting_app_names", frozenset())
            self._conflict_monitor.set_conflicts(bundle_ids=bundle_ids, app_names=app_names)

    @property
    def connected_device_id(self) -> DeviceId | None:
        """Which known model is plugged in, for diagnostics."""
        if self._input_source is not None and hasattr(self._input_source, "connected_device"):
            return getattr(self._input_source.connected_device, "device_id", None)
        if self._worker is not None:
            return getattr(self._worker.connected_device, "device_id", None)
        return None

    @property
    def connected_device_name(self) -> str:
        """Human-readable model name of the plugged-in device, or default."""
        dev_id = self.connected_device_id
        if dev_id is not None:
            return getattr(dev_id, "model", str(dev_id))
        if self._input_source is not None and hasattr(self._input_source, "name"):
            return self._input_source.name
        return "MuteMe"

    @property
    def input_source_name(self) -> str:
        """Human-readable name of the active input source."""
        if self._input_source is not None and hasattr(self._input_source, "name"):
            return self._input_source.name
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
            from muteme_flow.envious_wispr_adapter import EnviousWisprBackend
            from muteme_flow.main_thread import post_to_main
            from muteme_flow.wispr_adapter import WisprFlowBackend
            from muteme_flow.wispr_presence import WisprPresence

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

    def switch_input(self, input_choice: str) -> None:
        """Switch active input source, halting recording and reconfiguring conflict monitoring."""
        # 1. Resolve new input first to preserve active device if input_choice is invalid
        if self._input_factory is not None:
            new_input = self._input_factory(input_choice)
        else:
            new_input = self._default_input_factory(input_choice)

        # 2. Reset previous hardware connection state: stops recording and resets flags
        self.controller.machine.device_detached()

        # 3. Stop previous hardware listener
        if self._input_source is not None:
            self._input_source.stop()
        elif self._worker is not None:
            self._worker.stop()

        self._input_source = new_input
        self._worker = getattr(new_input, "worker", None)

        # 4. Synchronize conflict monitor with the incoming input's declared conflicts
        self._update_conflict_monitor(new_input)

        # 5. Start new hardware listener if runtime is running
        if not self._stopped and self._input_source is not None:
            self._input_source.start(self.controller.on_device_event)

        self.controller.schedule_refresh()

    def _default_input_factory(self, input_choice: str) -> InputSource:
        """Instantiate the default hardware adapter for a given input choice."""
        if input_choice == "muteme":
            from muteme_flow.hidapi_device import open_first_known
            from muteme_flow.led import LedMailbox
            from muteme_flow.muteme_adapter import MuteMeInputSource

            led_mailbox = self._led_mailbox
            if led_mailbox is None:
                led_mailbox = LedMailbox()
            return MuteMeInputSource(connect=open_first_known, led_mailbox=led_mailbox)
        raise ValueError(f"Unknown input source: {input_choice}")

    def set_audio_feedback(self, enabled: bool) -> None:
        """Enable or disable audible feedback chimes."""
        if self._audio_sink is not None and hasattr(self._audio_sink, "enabled"):
            self._audio_sink.enabled = enabled

    @classmethod
    def create_default(
        cls,
        timings: Timings | None = None,
        backend_choice: str = "wispr-flow",
        input_choice: str = "muteme",
        audio_feedback: bool = False,
        conflict_monitor: Any = None,
    ) -> "Runtime":
        """Build the real macOS runtime. Call on the main thread, before the run loop.

        Args:
            timings: Hold threshold and debounce timings for button interactions.
            backend_choice: Initial active dictation engine ('wispr-flow' or 'envious-wispr').
            input_choice: Initial active input device ('muteme').
            audio_feedback: Whether audio chime feedback is initially enabled.
            conflict_monitor: Optional ConflictMonitor instance to synchronize with inputs.
        """
        if input_choice != "muteme":
            raise ValueError(f"Unknown input source: {input_choice}")

        from muteme_flow.envious_wispr_adapter import EnviousWisprBackend
        from muteme_flow.feedback_sinks import AudioFeedbackSink, CompositeFeedbackSink
        from muteme_flow.hidapi_device import open_first_known, preload_hidapi
        from muteme_flow.led import LedMailbox
        from muteme_flow.main_thread import post_to_main
        from muteme_flow.muteme_adapter import MuteMeInputSource, MuteMeLedSink
        from muteme_flow.power import PowerObserver
        from muteme_flow.scheduler import NSTimerScheduler
        from muteme_flow.wispr_adapter import WisprFlowBackend
        from muteme_flow.wispr_presence import WisprPresence

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

        if input_choice == "muteme":
            input_source = MuteMeInputSource(connect=open_first_known, led_mailbox=led)
        else:
            raise ValueError(f"Unknown input source: {input_choice}")

        return cls(
            controller=controller,
            worker=getattr(input_source, "worker", None),
            input_source=input_source,
            presence=presence,
            make_power=lambda on_sleep, on_wake: PowerObserver.for_current_app(on_sleep, on_wake),
            audio_sink=audio_sink,
            conflict_monitor=conflict_monitor,
            led_mailbox=led,
        )

    def start(self) -> None:
        self._presence.start()
        self._power.start()
        if self._input_source is not None:
            self._input_source.start(self.controller.on_device_event)
            self._worker = getattr(self._input_source, "worker", self._worker)
        elif self._worker is not None:
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
            if self._input_source is not None:
                self._input_source.stop()
            elif self._worker is not None:
                self._worker.stop()

    def sleep(self) -> None:
        if self._input_source is not None and hasattr(self._input_source, "pause"):
            self._input_source.pause()
        elif self._worker is not None:
            self._worker.pause()

    def wake(self) -> None:
        # Reconnect first, then resync Wispr (specs/spec.md section 4.5).
        if self._input_source is not None and hasattr(self._input_source, "resume"):
            self._input_source.resume()
        elif self._worker is not None:
            self._worker.resume()
        self.controller.wake()

    def _drain(self) -> None:
        deadline = time.monotonic() + SHUTDOWN_DRAIN_S
        while self.controller.outstanding_dispatches > 0 and time.monotonic() < deadline:
            self._pump(_DRAIN_STEP_S)
