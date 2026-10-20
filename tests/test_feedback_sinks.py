from muteme_flow.feedback_sinks import (
    AudioFeedbackSink,
    CompositeFeedbackSink,
    NullFeedbackSink,
    preload_system_sounds,
)
from muteme_flow.protocols import FeedbackSink, FeedbackState


def test_null_feedback_sink():
    sink = NullFeedbackSink()
    assert isinstance(sink, FeedbackSink)
    assert sink.last_state is None

    sink.set_state(FeedbackState.RECORDING)
    assert sink.last_state is FeedbackState.RECORDING

    sink.mark_for_resend()
    assert sink.last_state is FeedbackState.RECORDING


def test_audio_feedback_sink_triggers_sounds_on_transitions():
    played = []
    sink = AudioFeedbackSink(player=played.append)
    assert isinstance(sink, FeedbackSink)
    assert sink.current_state == FeedbackState.IDLE

    # Transition IDLE -> RECORDING
    sink.set_state(FeedbackState.RECORDING)
    assert played == [AudioFeedbackSink.START_SOUND]
    assert sink.current_state == FeedbackState.RECORDING

    # Redundant state does not replay
    sink.set_state(FeedbackState.RECORDING)
    assert played == [AudioFeedbackSink.START_SOUND]

    # Transition RECORDING -> IDLE
    sink.set_state(FeedbackState.IDLE)
    assert played == [AudioFeedbackSink.START_SOUND, AudioFeedbackSink.STOP_SOUND]
    assert sink.current_state == FeedbackState.IDLE

    # Transition IDLE -> WARNING
    sink.set_state(FeedbackState.WARNING)
    assert played == [
        AudioFeedbackSink.START_SOUND,
        AudioFeedbackSink.STOP_SOUND,
        AudioFeedbackSink.WARNING_SOUND,
    ]
    assert sink.current_state == FeedbackState.WARNING


def test_preload_system_sounds_is_safe():
    preload_system_sounds()


def test_audio_feedback_sink_disabled():
    played = []
    sink = AudioFeedbackSink(player=played.append, enabled=False)

    sink.set_state(FeedbackState.RECORDING)
    sink.set_state(FeedbackState.IDLE)
    assert played == []


def test_audio_feedback_sink_mark_for_resend_is_safe_noop():
    played = []
    sink = AudioFeedbackSink(player=played.append)
    sink.mark_for_resend()
    assert played == []
    sink.set_state(FeedbackState.RECORDING)
    sink.mark_for_resend()
    assert played == [AudioFeedbackSink.START_SOUND]


def test_composite_feedback_sink():
    null1 = NullFeedbackSink()
    null2 = NullFeedbackSink()
    composite = CompositeFeedbackSink([null1, null2])
    assert isinstance(composite, FeedbackSink)
    assert len(composite.sinks) == 2

    # Verify sinks property returns a defensive copy
    composite.sinks.append(NullFeedbackSink())
    assert len(composite.sinks) == 2

    composite.set_state(FeedbackState.RECORDING)
    assert null1.last_state is FeedbackState.RECORDING
    assert null2.last_state is FeedbackState.RECORDING

    composite.mark_for_resend()


def test_composite_feedback_sink_survives_failing_sink():
    class FailingSink:
        def set_state(self, state):
            raise RuntimeError("sink error")

        def mark_for_resend(self):
            raise RuntimeError("resend error")

    null = NullFeedbackSink()
    composite = CompositeFeedbackSink([FailingSink(), null])

    # Should not raise exception
    composite.set_state(FeedbackState.WARNING)
    assert null.last_state is FeedbackState.WARNING

    composite.mark_for_resend()


def test_audio_feedback_sink_mark_for_resend():
    sounds = []
    sink = AudioFeedbackSink(player=sounds.append)
    sink.set_state(FeedbackState.RECORDING)
    assert sounds == [AudioFeedbackSink.START_SOUND]

    # mark_for_resend must be a no-op that does not trigger audio cues
    sink.mark_for_resend()
    assert sounds == [AudioFeedbackSink.START_SOUND]
