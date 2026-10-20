from collections.abc import Callable

import pytest

from muteme_flow.commands import Command
from muteme_flow.hid_worker import DeviceEvent
from muteme_flow.led import Color
from muteme_flow.protocols import (
    DictationBackend,
    DictationCommand,
    DictationCompletion,
    FeedbackSink,
    FeedbackState,
    InputEvent,
    InputEventHandler,
    InputSource,
    color_to_feedback_state,
    command_to_dictation_command,
    device_event_to_input_event,
    dictation_command_to_command,
    feedback_state_to_color,
    input_event_to_device_event,
)


class DummyInputSource:
    @property
    def name(self) -> str:
        return "Dummy Source"

    def start(self, on_event: InputEventHandler) -> None:
        pass

    def stop(self) -> None:
        pass


class DummyFeedbackSink:
    def set_state(self, state: FeedbackState) -> None:
        pass

    def mark_for_resend(self) -> None:
        pass


class DummyBackend:
    @property
    def name(self) -> str:
        return "Dummy Backend"

    @property
    def bundle_id(self) -> str | None:
        return "com.example.dummy"

    def dispatch(self, command: DictationCommand, on_complete: DictationCompletion) -> None:
        pass

    def is_running(self) -> bool:
        return True

    def start_presence_watch(self, on_change: Callable[[bool], None]) -> None:
        pass

    def stop_presence_watch(self) -> None:
        pass


def test_input_source_protocol_conformance():
    assert isinstance(DummyInputSource(), InputSource)
    assert not isinstance(object(), InputSource)


def test_feedback_sink_protocol_conformance():
    assert isinstance(DummyFeedbackSink(), FeedbackSink)
    assert not isinstance(object(), FeedbackSink)


def test_dictation_backend_protocol_conformance():
    assert isinstance(DummyBackend(), DictationBackend)
    assert not isinstance(object(), DictationBackend)


@pytest.mark.parametrize(
    ("color", "state"),
    [
        (Color.OFF, FeedbackState.OFF),
        (Color.RED, FeedbackState.IDLE),
        (Color.GREEN, FeedbackState.RECORDING),
        (Color.YELLOW, FeedbackState.WARNING),
        (Color.BLUE, FeedbackState.DISCONNECTED),
    ],
)
def test_color_and_feedback_state_bijective_mapping(color, state):
    assert color_to_feedback_state(color) is state
    assert feedback_state_to_color(state) is color


@pytest.mark.parametrize(
    ("device_event", "input_event"),
    [
        (DeviceEvent.CONNECTED, InputEvent.CONNECTED),
        (DeviceEvent.DISCONNECTED, InputEvent.DISCONNECTED),
        (DeviceEvent.OPEN_FAILED, InputEvent.OPEN_FAILED),
        (DeviceEvent.DOWN, InputEvent.DOWN),
        (DeviceEvent.UP, InputEvent.UP),
    ],
)
def test_device_and_input_event_bijective_mapping(device_event, input_event):
    assert device_event_to_input_event(device_event) is input_event
    assert input_event_to_device_event(input_event) is device_event


@pytest.mark.parametrize(
    ("command", "dictation_cmd"),
    [
        (Command.START, DictationCommand.START),
        (Command.STOP, DictationCommand.STOP),
    ],
)
def test_command_and_dictation_command_bijective_mapping(command, dictation_cmd):
    assert command_to_dictation_command(command) is dictation_cmd
    assert dictation_command_to_command(dictation_cmd) is command


def test_mapping_functions_raise_value_error_for_invalid_values():
    with pytest.raises(ValueError, match="No FeedbackState mapping for Color"):
        color_to_feedback_state(999)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No Color mapping for FeedbackState"):
        feedback_state_to_color("invalid")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No InputEvent mapping for DeviceEvent"):
        device_event_to_input_event("invalid")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No DeviceEvent mapping for InputEvent"):
        input_event_to_device_event("invalid")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No DictationCommand mapping for Command"):
        command_to_dictation_command("invalid")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="No Command mapping for DictationCommand"):
        dictation_command_to_command("invalid")  # type: ignore[arg-type]
