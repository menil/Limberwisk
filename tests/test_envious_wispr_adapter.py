import pytest

from muteme_flow.envious_wispr_adapter import (
    ENVIOUS_WISPR_BUNDLE_ID,
    EnviousWisprBackend,
    EnviousWisprCommand,
)
from muteme_flow.protocols import (
    DictationBackend,
    DictationCommand,
)


class FakeDispatcher:
    """Test double recording dispatched commands and simulating immediate success."""

    def __init__(self) -> None:
        self.dispatched = []

    def dispatch(self, command, on_complete) -> None:
        self.dispatched.append(command)
        on_complete(None)


class FakePresence:
    """Test double simulating application lifecycle notifications."""

    def __init__(self, on_change) -> None:
        self.on_change = on_change
        self.started = False
        self.stopped = False
        self._running = False

    def start(self) -> None:
        self.started = True
        self.on_change(self._running)

    def stop(self) -> None:
        self.stopped = True

    def is_running(self) -> bool:
        return self._running

    def set_running(self, running: bool) -> None:
        self._running = running
        self.on_change(running)


def test_envious_wispr_commands():
    assert EnviousWisprCommand.START.url == "envious-wispr://start-dictation"
    assert EnviousWisprCommand.STOP.url == "envious-wispr://stop-dictation"


def test_envious_wispr_backend_conformance():
    dispatcher = FakeDispatcher()
    backend = EnviousWisprBackend(dispatcher)
    assert isinstance(backend, DictationBackend)
    assert backend.name == "EnviousWispr"
    assert backend.bundle_id == ENVIOUS_WISPR_BUNDLE_ID


def test_envious_wispr_backend_dispatch():
    dispatcher = FakeDispatcher()
    backend = EnviousWisprBackend(dispatcher)
    results = []

    backend.dispatch(DictationCommand.START, results.append)
    assert dispatcher.dispatched == [EnviousWisprCommand.START]
    assert results == [None]

    backend.dispatch(DictationCommand.STOP, results.append)
    assert dispatcher.dispatched == [EnviousWisprCommand.START, EnviousWisprCommand.STOP]
    assert results == [None, None]

    # Directly dispatch vendor command
    backend.dispatch(EnviousWisprCommand.START, results.append)
    assert dispatcher.dispatched == [
        EnviousWisprCommand.START,
        EnviousWisprCommand.STOP,
        EnviousWisprCommand.START,
    ]

    with pytest.raises(ValueError, match="Expected DictationCommand"):
        backend.dispatch("invalid", results.append)  # type: ignore[arg-type]


def test_envious_wispr_backend_presence():
    dispatcher = FakeDispatcher()
    fake_presence = None

    def make_presence(on_change):
        nonlocal fake_presence
        fake_presence = FakePresence(on_change)
        return fake_presence

    backend = EnviousWisprBackend(dispatcher, presence_factory=make_presence)
    notifications = []

    backend.start_presence_watch(notifications.append)
    assert fake_presence is not None
    assert fake_presence.started
    assert not backend.is_running()

    fake_presence.set_running(True)
    assert backend.is_running()
    assert notifications == [False, True]

    # Re-entrant start_presence_watch stops previous instance
    backend.start_presence_watch(notifications.append)
    assert fake_presence.started

    backend.stop_presence_watch()
    assert fake_presence.stopped is True
    assert backend.presence is None
    assert backend.is_running() is False
