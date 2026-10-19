import logging

import pytest
from support.clock import FakeClock
from support.fake_scheduler import FakeScheduler

from muteme_flow.commands import Command
from muteme_flow.controller import Controller
from muteme_flow.hid_worker import DeviceEvent
from muteme_flow.led import Color, LedMailbox
from muteme_flow.state_machine import State


class Rig:
    def __init__(self):
        self.scheduler = FakeScheduler()
        self.posted = []
        self.dispatched = []
        self.led = LedMailbox()
        self.dispatch_error = None
        self.controller = Controller(
            dispatcher=self,
            led=self.led,
            scheduler=self.scheduler,
            post_to_main=self.posted.append,
        )
        self.controller.wispr_running_changed(True)
        self.run_posted()  # the machine's startup refresh is posted; start from a clean queue

    # the dispatcher interface
    def dispatch(self, command, on_complete):
        if self.dispatch_error:
            raise self.dispatch_error
        self.dispatched.append((command, on_complete))

    def run_posted(self):
        while self.posted:
            self.posted.pop(0)()

    def event(self, event):
        self.controller.on_device_event(event)
        self.run_posted()

    @property
    def machine(self):
        return self.controller.machine


@pytest.fixture
def rig():
    return Rig()


def test_device_events_are_posted_not_handled_on_the_calling_thread(rig):
    rig.controller.on_device_event(DeviceEvent.DOWN)
    assert rig.machine.state is State.IDLE  # nothing happened yet
    assert len(rig.posted) == 1
    rig.run_posted()
    assert rig.machine.state is State.PENDING_TOUCH


def test_every_device_event_reaches_the_state_machine(rig):
    rig.event(DeviceEvent.CONNECTED)
    assert rig.machine.device_connected
    rig.event(DeviceEvent.OPEN_FAILED)
    assert rig.machine.open_failed
    rig.event(DeviceEvent.DOWN)
    rig.scheduler.advance(0.1)
    rig.event(DeviceEvent.UP)
    assert rig.machine.state is State.RECORDING_LOCKED
    rig.event(DeviceEvent.DISCONNECTED)
    assert not rig.machine.device_connected
    assert [command for command, _ in rig.dispatched] == [Command.START, Command.STOP]


def test_the_machine_is_given_the_time_the_event_was_received_not_processed(rig):
    rig.controller.on_device_event(DeviceEvent.DOWN)  # received at t0
    rig.scheduler.advance(0.1)
    rig.controller.on_device_event(DeviceEvent.UP)  # received at t0 + 0.1
    rig.scheduler.advance(2.0)  # the main thread only gets to both much later
    rig.run_posted()
    assert rig.machine.state is State.RECORDING_LOCKED  # a tap, not a hold


def test_the_led_requests_go_to_the_mailbox(rig):
    rig.event(DeviceEvent.DOWN)
    assert rig.led.take_pending() is Color.GREEN


def test_completions_report_back_to_the_machine(rig):
    rig.event(DeviceEvent.DOWN)
    _, done = rig.dispatched[0]
    done(RuntimeError("nope"))
    assert rig.machine.state is State.IDLE
    assert rig.machine.command_failed


def test_outstanding_dispatches_are_counted_until_they_complete(rig):
    assert rig.controller.outstanding_dispatches == 0
    rig.event(DeviceEvent.DOWN)
    assert rig.controller.outstanding_dispatches == 1
    rig.dispatched[0][1](None)
    assert rig.controller.outstanding_dispatches == 0


def test_a_completion_that_raises_still_releases_the_outstanding_count(rig):
    # Shutdown waits for this count to reach zero, so a faulty completion must not hold it up.
    rig.event(DeviceEvent.DOWN)
    _, done = rig.dispatched[0]

    def broken(*_args):
        raise RuntimeError("machine bug")

    rig.machine._dispatch_finished = broken
    with pytest.raises(RuntimeError, match="machine bug"):
        done(None)
    assert rig.controller.outstanding_dispatches == 0


def test_a_dispatcher_that_raises_ends_in_the_failure_path_without_reentering(rig):
    rig.dispatch_error = RuntimeError("PyObjC blew up")
    rig.controller.on_device_event(DeviceEvent.DOWN)
    rig.posted.pop(0)()  # handling the touch must not raise
    # The failure is delivered by a later post, not inline during the transition.
    assert rig.machine.state is State.PENDING_TOUCH
    rig.run_posted()
    assert rig.machine.state is State.IDLE
    assert rig.machine.command_failed
    assert rig.controller.outstanding_dispatches == 0


def test_an_exception_in_a_handler_is_logged_and_the_latency_input_is_cleared(rig, caplog):
    rig.machine.touch_down = lambda at: (_ for _ in ()).throw(RuntimeError("machine bug"))
    rig.controller._handlers[DeviceEvent.DOWN] = lambda at: rig.machine.touch_down(at)
    with caplog.at_level(logging.ERROR):
        rig.event(DeviceEvent.DOWN)
    assert "machine bug" in caplog.text
    rig.controller.latency.dispatched()  # no input in progress, so nothing is recorded
    assert rig.controller.latency.samples_ms == []


def test_latency_is_recorded_after_the_command_is_handed_over():
    clock = FakeClock(start=0.0)
    scheduler = FakeScheduler()
    scheduler.now = clock

    class SlowDispatcher:
        def dispatch(self, command, on_complete):
            clock.advance(0.010)  # submitting the command takes 10 ms

    posted = []
    controller = Controller(
        dispatcher=SlowDispatcher(),
        led=LedMailbox(),
        scheduler=scheduler,
        post_to_main=posted.append,
    )
    controller.wispr_running_changed(True)
    controller.on_device_event(DeviceEvent.DOWN)
    clock.advance(0.004)  # waiting for the main thread takes 4 ms
    posted.pop()()
    assert controller.latency.samples_ms == [pytest.approx(14.0)]


def test_shutdown_goes_straight_to_the_machine(rig):
    rig.event(DeviceEvent.DOWN)
    rig.controller.shutdown()
    assert [command for command, _ in rig.dispatched] == [Command.START, Command.STOP]
    assert rig.led.take_pending() is Color.RED


def test_a_conflict_report_reaches_the_machine(rig):
    rig.controller.conflict_changed(True)
    assert rig.machine.conflict


def test_the_ui_is_refreshed_after_the_touch_is_handled_not_during_it(rig):
    seen = []
    rig.controller.on_change = lambda: seen.append(rig.dispatched[:])
    rig.event(DeviceEvent.DOWN)
    # Refreshing before the dispatch would have seen no command yet.
    assert seen
    assert all(len(commands) == 1 for commands in seen)


def test_a_burst_of_changes_causes_one_refresh(rig):
    refreshes = []
    rig.controller.on_change = lambda: refreshes.append(1)
    rig.run_posted()
    refreshes.clear()
    rig.controller.conflict_changed(True)
    rig.controller.conflict_changed(False)
    rig.controller.conflict_changed(True)
    assert refreshes == []  # nothing inline
    rig.run_posted()
    assert refreshes == [1]


def test_a_failing_refresh_is_logged_and_does_not_disturb_the_state_machine(rig, caplog):
    def broken():
        raise RuntimeError("menu bug")

    rig.controller.on_change = broken
    with caplog.at_level(logging.ERROR):
        rig.event(DeviceEvent.DOWN)
    assert "menu bug" in caplog.text
    assert rig.machine.state is State.PENDING_TOUCH
    assert [command for command, _ in rig.dispatched] == [Command.START]
