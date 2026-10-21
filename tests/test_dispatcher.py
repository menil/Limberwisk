import pytest
from support.fake_appkit import FakeConfiguration, FakeWorkspace

from limberwisk.commands import Command
from limberwisk.dispatcher import WISPR_BUNDLE_ID, DispatchError, NSWorkspaceDispatcher


class Rig:
    def __init__(self, installed=True):
        self.workspace = FakeWorkspace(installed=installed)
        self.configuration = FakeConfiguration()
        self.posted = []
        self.results = []
        self.dispatcher = NSWorkspaceDispatcher(
            self.posted.append,
            workspace=self.workspace,
            make_configuration=lambda: self.configuration,
            make_url=lambda text: f"URL({text})",
        )

    def dispatch(self, command):
        self.dispatcher.dispatch(command, self.results.append)

    def run_posted(self):
        for fn in self.posted:
            fn()
        self.posted.clear()


@pytest.fixture
def rig():
    return Rig()


@pytest.mark.parametrize(
    ("command", "url"),
    [
        (Command.START, "wispr-flow://start-hands-free"),
        (Command.STOP, "wispr-flow://stop-hands-free"),
    ],
)
def test_opens_the_command_url_with_wispr_flow_itself(rig, command, url):
    rig.dispatch(command)
    request = rig.workspace.opened[0]
    assert request["urls"] == [f"URL({url})"]
    assert request["app_url"] == "file:///Applications/Wispr%20Flow.app"
    assert rig.workspace.requested_bundle_ids == [WISPR_BUNDLE_ID]


def test_never_activates_wispr_flow(rig):
    rig.dispatch(Command.START)
    assert rig.configuration.activates is False


def test_success_is_reported_on_the_main_thread_not_the_completion_queue(rig):
    rig.dispatch(Command.START)
    rig.workspace.opened[0]["handler"](None, None)
    assert rig.results == []  # nothing yet: it was only posted
    rig.run_posted()
    assert rig.results == [None]


def test_an_error_from_launch_services_becomes_a_dispatch_error(rig):
    rig.dispatch(Command.STOP)
    rig.workspace.opened[0]["handler"](None, "launch failed")
    rig.run_posted()
    assert isinstance(rig.results[0], DispatchError)
    assert "launch failed" in str(rig.results[0])


def test_a_missing_wispr_flow_is_reported_without_opening_anything():
    rig = Rig(installed=False)
    rig.dispatch(Command.START)
    rig.run_posted()
    assert rig.workspace.opened == []
    assert isinstance(rig.results[0], DispatchError)
    assert "not installed" in str(rig.results[0])


def test_a_synchronous_failure_is_reported_through_the_same_path(rig):
    rig.workspace.open_error = RuntimeError("bad URL")
    rig.dispatch(Command.START)  # must not raise
    rig.run_posted()
    assert isinstance(rig.results[0], DispatchError)
    assert "bad URL" in str(rig.results[0])


def test_the_completion_is_never_called_inline(rig):
    rig.dispatch(Command.STOP)
    assert rig.results == []
