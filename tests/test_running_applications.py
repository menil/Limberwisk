import logging

from support.fake_appkit import FakeKvoObserver, FakeKvoWorkspace

from limberwisk.running_applications import RUNNING_APPLICATIONS_KEY, RunningApplicationsWatch


class Harness:
    def __init__(self):
        self.workspace = FakeKvoWorkspace()
        self.observers: list[FakeKvoObserver] = []
        self.posted: list = []
        self.watch = RunningApplicationsWatch(
            self.workspace, post=self.posted.append, make_observer=self._make_observer
        )

    def _make_observer(self, callback):
        observer = FakeKvoObserver(callback)
        self.observers.append(observer)
        return observer

    def run_posted(self):
        """Let the main thread drain what was queued for it."""
        queued, self.posted = self.posted, []
        for fn in queued:
            fn()


def test_start_observes_the_running_applications_key_without_asking_for_values():
    harness = Harness()
    harness.watch.start(lambda: None)
    [(observer, key_path, options, _context)] = harness.workspace.added
    assert observer is harness.observers[0]
    assert key_path == RUNNING_APPLICATIONS_KEY == "runningApplications"
    assert options == 0  # the handler re-queries; it never reads the change dictionary


def test_a_change_reaches_the_handler_only_via_the_main_thread_poster():
    harness = Harness()
    calls = []
    harness.watch.start(lambda: calls.append(1))
    harness.observers[0].fire()
    assert calls == []  # KVO fires on whichever thread changed the list
    harness.run_posted()
    assert calls == [1]


def test_a_failing_handler_is_logged_not_raised(caplog):
    harness = Harness()

    def boom():
        raise RuntimeError("handler bug")

    harness.watch.start(boom)
    harness.observers[0].fire()
    with caplog.at_level(logging.ERROR):
        harness.run_posted()
    assert "handler bug" in caplog.text


def test_stop_removes_the_observer_once_and_is_repeatable():
    harness = Harness()
    harness.watch.start(lambda: None)
    harness.watch.stop()
    harness.watch.stop()
    assert harness.workspace.removed == [(harness.observers[0], RUNNING_APPLICATIONS_KEY)]


def test_stop_without_start_does_nothing():
    harness = Harness()
    harness.watch.stop()
    # Removing an observer that was never added raises in Cocoa, so it must not be tried.
    assert harness.workspace.removed == []


def test_starting_twice_registers_only_one_observer():
    harness = Harness()
    harness.watch.start(lambda: None)
    harness.watch.start(lambda: None)
    assert len(harness.workspace.added) == 1


def test_a_change_queued_before_stop_is_dropped_after_it():
    harness = Harness()
    calls = []
    harness.watch.start(lambda: calls.append(1))
    harness.observers[0].fire()
    harness.watch.stop()
    harness.run_posted()
    assert calls == []  # a stopped presence must not report, e.g. after a backend switch


def test_the_watch_can_be_started_again_after_a_stop():
    harness = Harness()
    calls = []
    harness.watch.start(lambda: calls.append("old"))
    harness.watch.stop()
    harness.watch.start(lambda: calls.append("new"))
    assert len(harness.workspace.added) == 2
    harness.observers[0].fire()  # the old observer is dead
    harness.observers[1].fire()
    harness.run_posted()
    assert calls == ["new"]
