from limberwisk.commands import WISPR_BUNDLE_ID, Command
from limberwisk.protocols import (
    DictationBackend,
    DictationCommand,
)
from limberwisk.wispr_adapter import WisprFlowBackend


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


def test_wispr_flow_backend_conformance():
    dispatcher = FakeDispatcher()
    backend = WisprFlowBackend(dispatcher)
    assert isinstance(backend, DictationBackend)
    assert backend.name == "Wispr Flow"
    assert backend.bundle_id == WISPR_BUNDLE_ID


def test_wispr_flow_backend_custom_identity():
    dispatcher = FakeDispatcher()
    backend = WisprFlowBackend(
        dispatcher,
        name="Custom Engine",
        bundle_id="com.example.custom",
    )
    assert backend.name == "Custom Engine"
    assert backend.bundle_id == "com.example.custom"


def test_wispr_flow_backend_dispatch():
    dispatcher = FakeDispatcher()
    backend = WisprFlowBackend(dispatcher)
    results = []

    backend.dispatch(DictationCommand.START, results.append)
    assert dispatcher.dispatched == [Command.START]
    assert results == [None]

    backend.dispatch(DictationCommand.STOP, results.append)
    assert dispatcher.dispatched == [Command.START, Command.STOP]
    assert results == [None, None]


def test_wispr_flow_backend_presence():
    dispatcher = FakeDispatcher()
    fake_presence = None

    def make_presence(on_change):
        nonlocal fake_presence
        fake_presence = FakePresence(on_change)
        return fake_presence

    backend = WisprFlowBackend(dispatcher, presence_factory=make_presence)
    notifications = []

    backend.start_presence_watch(notifications.append)
    assert fake_presence is not None
    assert fake_presence.started
    assert not backend.is_running()

    fake_presence.set_running(True)
    assert backend.is_running()
    assert notifications == [False, True]

    backend.stop_presence_watch()
    assert fake_presence.stopped
