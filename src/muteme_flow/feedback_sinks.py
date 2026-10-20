"""Feedback sink implementations for hardware without LEDs and audio cues."""

import logging
from collections.abc import Callable, Sequence
from typing import Any

from muteme_flow.protocols import FeedbackSink, FeedbackState

log = logging.getLogger(__name__)

SoundPlayer = Callable[[str], None]

_SOUND_CACHE: dict[str, Any] = {}


class NullFeedbackSink(FeedbackSink):
    """A no-op feedback sink for silent hardware, foot pedals, or headless runs."""

    def __init__(self) -> None:
        self.last_state: FeedbackState | None = None

    def set_state(self, state: FeedbackState) -> None:
        self.last_state = state

    def mark_for_resend(self) -> None:
        pass


def preload_system_sounds() -> None:
    """Preload and cache system audio cues into memory to eliminate disk I/O latency."""
    try:
        from AppKit import NSSound

        for name in (
            AudioFeedbackSink.START_SOUND,
            AudioFeedbackSink.STOP_SOUND,
            AudioFeedbackSink.WARNING_SOUND,
        ):
            sound = NSSound.soundNamed_(name)
            if sound is not None:
                _SOUND_CACHE[name] = sound
    except Exception:
        # AppKit unavailable (Linux/test environment) or sound file not found.
        pass


def _play_appkit_sound(sound_name: str) -> None:
    """Default sound player using AppKit.NSSound."""
    try:
        sound = _SOUND_CACHE.get(sound_name)
        if sound is None:
            from AppKit import NSSound

            sound = NSSound.soundNamed_(sound_name)
            if sound is not None:
                _SOUND_CACHE[sound_name] = sound
        if sound is not None:
            sound.play()
    except Exception:
        log.exception("failed to play system sound %s", sound_name)


class AudioFeedbackSink(FeedbackSink):
    """Plays system sound cues on feedback state changes."""

    # Default macOS system sounds
    START_SOUND = "Tink"
    STOP_SOUND = "Pop"
    WARNING_SOUND = "Basso"

    def __init__(
        self,
        player: SoundPlayer = _play_appkit_sound,
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the audio feedback sink with an optional sound player."""
        self._player = player
        self.enabled = enabled
        self._current_state: FeedbackState = FeedbackState.IDLE
        # Warm audio cache on creation so the first touch transition has zero disk lookup latency.
        if player is _play_appkit_sound:
            preload_system_sounds()

    @property
    def current_state(self) -> FeedbackState:
        """Current tracked feedback state."""
        return self._current_state

    def set_state(self, state: FeedbackState) -> None:
        """Play distinct sound cues on state changes."""
        prev = self._current_state
        self._current_state = state

        if not self.enabled or prev == state:
            return

        if state == FeedbackState.RECORDING:
            self._player(self.START_SOUND)
        elif prev == FeedbackState.RECORDING and state == FeedbackState.IDLE:
            self._player(self.STOP_SOUND)
        elif state == FeedbackState.WARNING:
            self._player(self.WARNING_SOUND)

    def mark_for_resend(self) -> None:
        """Resend is a no-op for audio cues.

        Steady-state reassertions (such as hardware reconnects or system wake)
        must not re-trigger audible sounds when no user transition occurred.
        """
        pass


class CompositeFeedbackSink(FeedbackSink):
    """Multiplexes feedback to multiple sinks (e.g. LED + Audio click)."""

    def __init__(self, sinks: Sequence[FeedbackSink]) -> None:
        """Initialize with a sequence of child feedback sinks."""
        self._sinks = list(sinks)

    @property
    def sinks(self) -> list[FeedbackSink]:
        """Defensive copy of child feedback sinks."""
        return list(self._sinks)

    def set_state(self, state: FeedbackState) -> None:
        """Fan out state update to all registered sinks with fault isolation."""
        for sink in self._sinks:
            try:
                # Fault isolation: failure in one sink must not block others.
                sink.set_state(state)
            except Exception:
                log.exception("error updating feedback sink %r", sink)

    def mark_for_resend(self) -> None:
        """Fan out resend request to all registered sinks with fault isolation."""
        for sink in self._sinks:
            try:
                # Fault isolation: failure in one sink must not block others.
                sink.mark_for_resend()
            except Exception:
                log.exception("error re-sending to feedback sink %r", sink)
