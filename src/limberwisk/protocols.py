"""Pluggable input, feedback, and dictation backend protocols.

Enables modular support for alternative button devices (pedals, keypads) and
alternative dictation engines (Wispr Flow, EnviousWispr) while keeping the core
timing state machine decoupled.
"""

from collections.abc import Callable
from enum import Enum, auto
from typing import Protocol, runtime_checkable

from limberwisk.commands import Command
from limberwisk.hid_worker import DeviceEvent
from limberwisk.led import Color


class InputEvent(Enum):
    """Normalized hardware or virtual input events."""

    CONNECTED = auto()
    DISCONNECTED = auto()
    OPEN_FAILED = auto()
    DOWN = auto()
    UP = auto()


InputEventHandler = Callable[[InputEvent], None]


@runtime_checkable
class InputSource(Protocol):
    """A hardware or virtual input provider that emits button events."""

    @property
    def name(self) -> str:
        """Human-readable name of the input source."""
        ...

    def start(self, on_event: InputEventHandler) -> None:
        """Start listening for inputs; invoke `on_event(event)` on state changes."""
        ...

    def stop(self) -> None:
        """Stop listening and clean up all resources."""
        ...


class FeedbackState(Enum):
    """Semantic states rendered by peripheral feedback (LEDs, audio, etc.)."""

    OFF = auto()
    IDLE = auto()  # Standby / not dictating (MuteMe Red)
    RECORDING = auto()  # Dictation active (MuteMe Green)
    WARNING = auto()  # Warning / conflict / error (MuteMe Yellow)
    DISCONNECTED = auto()  # Target not running or device unplugged (MuteMe Blue)


@runtime_checkable
class FeedbackSink(Protocol):
    """Accepts high-level feedback states to render on hardware."""

    def set_state(self, state: FeedbackState) -> None:
        """Update the active feedback state."""
        ...

    def mark_for_resend(self) -> None:
        """Re-apply the current feedback state (e.g. after peripheral reconnect)."""
        ...


class DictationCommand(Enum):
    """Generic hands-free control commands dispatched to dictation backends."""

    START = auto()
    STOP = auto()


DictationCompletion = Callable[[Exception | None], None]


@runtime_checkable
class DictationBackend(Protocol):
    """A target dictation engine (e.g. Wispr Flow, EnviousWispr)."""

    @property
    def name(self) -> str:
        """Display name of the dictation engine."""
        ...

    @property
    def bundle_id(self) -> str | None:
        """macOS bundle identifier for process presence tracking, if applicable."""
        ...

    def dispatch(self, command: DictationCommand, on_complete: DictationCompletion) -> None:
        """Dispatch START or STOP to the backend; invokes on_complete on completion."""
        ...

    def is_running(self) -> bool:
        """Check whether the backend application is currently running."""
        ...

    def start_presence_watch(self, on_change: Callable[[bool], None]) -> None:
        """Subscribe to application launch/exit events."""
        ...

    def stop_presence_watch(self) -> None:
        """Unsubscribe from application launch/exit events."""
        ...


# Mapping helpers between existing types and the new protocols

_COLOR_TO_FEEDBACK = {
    Color.OFF: FeedbackState.OFF,
    Color.RED: FeedbackState.IDLE,
    Color.GREEN: FeedbackState.RECORDING,
    Color.YELLOW: FeedbackState.WARNING,
    Color.BLUE: FeedbackState.DISCONNECTED,
}

_FEEDBACK_TO_COLOR = {v: k for k, v in _COLOR_TO_FEEDBACK.items()}

_DEVICE_TO_INPUT_EVENT = {
    DeviceEvent.CONNECTED: InputEvent.CONNECTED,
    DeviceEvent.DISCONNECTED: InputEvent.DISCONNECTED,
    DeviceEvent.OPEN_FAILED: InputEvent.OPEN_FAILED,
    DeviceEvent.DOWN: InputEvent.DOWN,
    DeviceEvent.UP: InputEvent.UP,
}

_INPUT_TO_DEVICE_EVENT = {v: k for k, v in _DEVICE_TO_INPUT_EVENT.items()}

_COMMAND_TO_DICTATION = {
    Command.START: DictationCommand.START,
    Command.STOP: DictationCommand.STOP,
}

_DICTATION_TO_COMMAND = {v: k for k, v in _COMMAND_TO_DICTATION.items()}


def color_to_feedback_state(color: Color) -> FeedbackState:
    """Map a MuteMe hardware LED color to a semantic FeedbackState."""
    try:
        return _COLOR_TO_FEEDBACK[color]
    except KeyError:
        raise ValueError(f"No FeedbackState mapping for Color: {color}") from None


def feedback_state_to_color(state: FeedbackState) -> Color:
    """Map a semantic FeedbackState to a MuteMe hardware LED color."""
    try:
        return _FEEDBACK_TO_COLOR[state]
    except KeyError:
        raise ValueError(f"No Color mapping for FeedbackState: {state}") from None


def device_event_to_input_event(event: DeviceEvent) -> InputEvent:
    """Map a low-level DeviceEvent to an InputEvent."""
    try:
        return _DEVICE_TO_INPUT_EVENT[event]
    except KeyError:
        raise ValueError(f"No InputEvent mapping for DeviceEvent: {event}") from None


def input_event_to_device_event(event: InputEvent) -> DeviceEvent:
    """Map an InputEvent to a low-level DeviceEvent."""
    try:
        return _INPUT_TO_DEVICE_EVENT[event]
    except KeyError:
        raise ValueError(f"No DeviceEvent mapping for InputEvent: {event}") from None


def command_to_dictation_command(command: Command) -> DictationCommand:
    """Map a legacy Command to a DictationCommand."""
    try:
        return _COMMAND_TO_DICTATION[command]
    except KeyError:
        raise ValueError(f"No DictationCommand mapping for Command: {command}") from None


def dictation_command_to_command(command: DictationCommand) -> Command:
    """Map a DictationCommand to a legacy Command."""
    try:
        return _DICTATION_TO_COMMAND[command]
    except KeyError:
        raise ValueError(f"No Command mapping for DictationCommand: {command}") from None
