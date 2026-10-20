from support.fake_hid import FakeHidDevice

from muteme_flow.conflict import OFFICIAL_APP_BUNDLE_IDS
from muteme_flow.hid_worker import DeviceEvent
from muteme_flow.led import Color, LedMailbox
from muteme_flow.muteme_adapter import MuteMeInputSource, MuteMeLedSink
from muteme_flow.protocols import (
    FeedbackSink,
    FeedbackState,
    InputEvent,
    InputSource,
    device_event_to_input_event,
)


def test_muteme_led_sink_conformance():
    mailbox = LedMailbox()
    sink = MuteMeLedSink(mailbox)
    assert isinstance(sink, FeedbackSink)
    assert sink.mailbox is mailbox


def test_muteme_led_sink_maps_feedback_states_to_colors():
    mailbox = LedMailbox()
    sink = MuteMeLedSink(mailbox)

    sink.set_state(FeedbackState.RECORDING)
    assert mailbox.take_pending() is Color.GREEN

    sink.set_state(Color.YELLOW)
    assert mailbox.take_pending() is Color.YELLOW

    sink.set_state(FeedbackState.IDLE)
    assert mailbox.take_pending() is Color.RED

    sink.set_state(FeedbackState.WARNING)
    assert mailbox.take_pending() is Color.YELLOW

    sink.set_state(FeedbackState.DISCONNECTED)
    assert mailbox.take_pending() is Color.BLUE

    sink.set_state(FeedbackState.OFF)
    assert mailbox.take_pending() is Color.OFF

    import pytest

    with pytest.raises(ValueError, match="Expected FeedbackState or Color"):
        sink.set_state("invalid")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Expected FeedbackState or Color"):
        mailbox.set_state("invalid")  # type: ignore[arg-type]


def test_muteme_led_sink_mark_for_resend():
    mailbox = LedMailbox()
    sink = MuteMeLedSink(mailbox)
    sink.set_state(FeedbackState.WARNING)
    assert mailbox.take_pending() is Color.YELLOW

    sink.mark_for_resend()
    assert mailbox.take_pending() is Color.YELLOW


def test_led_mailbox_direct_conformance_to_feedback_sink():
    mailbox = LedMailbox()
    assert isinstance(mailbox, FeedbackSink)

    mailbox.set_state(FeedbackState.RECORDING)
    assert mailbox.take_pending() is Color.GREEN

    mailbox.set_state(Color.YELLOW)
    assert mailbox.take_pending() is Color.YELLOW


def test_muteme_input_source_conformance():
    mailbox = LedMailbox()
    source = MuteMeInputSource(connect=lambda: FakeHidDevice(), led_mailbox=mailbox)
    assert isinstance(source, InputSource)
    assert source.name == "MuteMe"
    assert source.conflicting_bundle_ids == OFFICIAL_APP_BUNDLE_IDS
    assert "MuteMe" in source.conflicting_app_names


def test_muteme_input_source_lifecycle_and_events():
    mailbox = LedMailbox()
    device = FakeHidDevice()
    events = []

    source = MuteMeInputSource(connect=lambda: device, led_mailbox=mailbox)
    source.start(events.append)

    try:
        assert source.worker is not None
        assert source.name == "MuteMe"
        assert device_event_to_input_event(DeviceEvent.DOWN) is InputEvent.DOWN

        # Test pause and resume delegating to underlying worker
        source.pause()
        assert source.worker._paused.is_set()
        source.resume()
        assert not source.worker._paused.is_set()
    finally:
        source.stop()
        assert source.worker is None
