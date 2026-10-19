import pytest
from support.fake_scheduler import FakeScheduler

from muteme_flow.commands import Command
from muteme_flow.led import Color
from muteme_flow.state_machine import (
    ERROR_FLASH_S,
    PERSISTENT_FAILURES,
    State,
    StateMachine,
    Timings,
)

HOLD = Timings().hold_s
DEBOUNCE = Timings().debounce_s
FAIL = RuntimeError("LaunchServices said no")


class Rig:
    """A state machine wired to recorders and a fake clock.

    Commands are recorded with their completion callbacks, which tests invoke by hand
    to model the outcome arriving later.
    """

    def __init__(self, wispr_running=True):
        self.scheduler = FakeScheduler()
        self.calls: list[tuple[Command, object]] = []
        self.leds: list[Color] = []
        self.machine = StateMachine(
            send=lambda command, done: self.calls.append((command, done)),
            set_led=self.leds.append,
            scheduler=self.scheduler,
        )
        self.machine.device_attached()
        if wispr_running:
            self.machine.wispr_running_changed(True)

    @property
    def sent(self):
        return [command for command, _ in self.calls]

    @property
    def led(self):
        return self.leds[-1]

    def complete(self, index, error=None):
        self.calls[index][1](error)

    def complete_all(self, error=None):
        for _, done in self.calls:
            done(error)

    def tap(self, duration=0.12):
        self.machine.touch_down()
        self.scheduler.advance(duration)
        self.machine.touch_up()
        self.scheduler.advance(0.2)  # clear of the debounce window

    def hold(self, duration=1.0):
        self.tap(duration)


@pytest.fixture
def rig():
    return Rig()


# --- tap-to-toggle and push-to-talk ----------------------------------------------


def test_starts_idle_with_a_red_led(rig):
    assert rig.machine.state is State.IDLE
    assert rig.led is Color.RED


def test_touch_down_starts_recording_immediately_and_turns_the_led_green(rig):
    rig.machine.touch_down()
    assert rig.sent == [Command.START]
    assert rig.machine.state is State.PENDING_TOUCH
    assert rig.led is Color.GREEN


def test_a_quick_tap_locks_recording_on_without_a_second_command(rig):
    rig.tap()
    assert rig.sent == [Command.START]
    assert rig.machine.state is State.RECORDING_LOCKED
    assert rig.led is Color.GREEN


def test_the_next_touch_down_stops_a_locked_recording(rig):
    rig.tap()
    rig.machine.touch_down()
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE
    assert rig.led is Color.RED


def test_the_release_that_ends_a_locked_recording_is_ignored(rig):
    rig.tap()
    rig.machine.touch_down()
    rig.scheduler.advance(0.1)
    rig.machine.touch_up()
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE


def test_holding_past_the_threshold_is_push_to_talk(rig):
    rig.machine.touch_down()
    rig.scheduler.advance(HOLD + 0.01)
    assert rig.machine.state is State.RECORDING_MOMENTARY
    rig.machine.touch_up()
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE
    assert rig.led is Color.RED


def test_releasing_just_before_the_threshold_is_still_a_tap(rig):
    rig.machine.touch_down()
    rig.scheduler.advance(HOLD - 0.01)
    rig.machine.touch_up()
    assert rig.machine.state is State.RECORDING_LOCKED


def test_the_hold_timer_is_cancelled_when_the_tap_releases(rig):
    rig.machine.touch_down()
    rig.scheduler.advance(0.1)
    rig.machine.touch_up()
    assert rig.scheduler.pending == 0
    rig.scheduler.advance(1.0)
    assert rig.machine.state is State.RECORDING_LOCKED


def test_a_tap_then_a_hold_then_a_tap_runs_three_gestures_cleanly(rig):
    rig.tap()  # lock on
    rig.tap()  # lock off
    rig.hold()  # push-to-talk
    assert rig.sent == [Command.START, Command.STOP, Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE


def test_the_led_is_lit_before_the_start_is_dispatched():
    order = []
    scheduler = FakeScheduler()
    machine = StateMachine(
        send=lambda command, done: order.append(command),
        set_led=lambda color: order.append(color),
        scheduler=scheduler,
    )
    machine.wispr_running_changed(True)
    order.clear()
    machine.touch_down()
    assert order == [Color.GREEN, Command.START]


# --- timing comes from when the HID thread saw the event -----------------------------


def test_a_slow_main_thread_does_not_turn_a_quick_tap_into_push_to_talk(rig):
    rig.machine.touch_down(at=10.0)
    rig.scheduler.advance(2.0)  # the main thread was busy: the hold timer fires late
    rig.machine.touch_up(at=10.12)  # but the finger was only down for 120 ms
    assert rig.machine.state is State.RECORDING_LOCKED


def test_a_long_press_is_push_to_talk_even_if_the_release_is_processed_late(rig):
    rig.machine.touch_down(at=10.0)
    rig.machine.touch_up(at=10.0 + HOLD + 0.1)  # hold timer never ran
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE


def test_debounce_uses_the_event_timestamps(rig):
    rig.machine.touch_down(at=5.0)
    rig.machine.touch_up(at=5.1)
    rig.scheduler.advance(5.0)  # processing was late, but the touches really were close
    rig.machine.touch_down(at=5.1 + DEBOUNCE / 2)
    assert rig.sent == [Command.START]


# --- debounce -------------------------------------------------------------------------


def test_a_touch_down_right_after_a_release_is_a_bounce_and_is_ignored(rig):
    rig.machine.touch_down()
    rig.scheduler.advance(0.1)
    rig.machine.touch_up()
    rig.scheduler.advance(DEBOUNCE / 2)
    rig.machine.touch_down()
    rig.scheduler.advance(0.05)
    rig.machine.touch_up()
    assert rig.sent == [Command.START]
    assert rig.machine.state is State.RECORDING_LOCKED


def test_a_touch_down_after_the_debounce_window_counts(rig):
    rig.machine.touch_down()
    rig.machine.touch_up()
    rig.scheduler.advance(DEBOUNCE + 0.001)
    rig.machine.touch_down()
    assert rig.sent == [Command.START, Command.STOP]


# --- Wispr Flow not running ------------------------------------------------------------


def test_touches_are_swallowed_while_wispr_is_not_running():
    rig = Rig(wispr_running=False)
    assert rig.led is Color.BLUE
    rig.tap()
    assert rig.sent == []
    assert rig.machine.state is State.IDLE


def test_the_led_returns_to_red_when_wispr_launches():
    rig = Rig(wispr_running=False)
    rig.machine.wispr_running_changed(True)
    assert rig.led is Color.RED


def test_quitting_wispr_mid_recording_goes_idle_without_sending_a_stop(rig):
    rig.tap()
    rig.machine.wispr_running_changed(False)
    assert rig.sent == [Command.START]  # no stop: it would relaunch Wispr
    assert rig.machine.state is State.IDLE
    assert rig.led is Color.BLUE


def test_quitting_wispr_while_the_button_is_held_ignores_the_release(rig):
    rig.machine.touch_down()
    rig.machine.wispr_running_changed(False)
    rig.machine.wispr_running_changed(True)
    rig.machine.touch_up()
    assert rig.machine.state is State.IDLE
    assert rig.sent == [Command.START]


def test_a_touch_that_began_while_wispr_was_away_does_not_start_when_it_returns(rig):
    rig.machine.wispr_running_changed(False)
    rig.machine.touch_down()
    rig.machine.wispr_running_changed(True)
    rig.scheduler.advance(0.1)
    rig.machine.touch_up()
    assert rig.sent == []
    assert rig.machine.state is State.IDLE


# --- dispatch failures (spec 4.7) -------------------------------------------------------


def test_a_failed_start_returns_to_idle_and_flashes_yellow_then_red(rig):
    rig.tap()
    rig.complete(0, FAIL)
    assert rig.machine.state is State.IDLE
    assert rig.led is Color.YELLOW
    assert rig.machine.command_failed
    rig.scheduler.advance(ERROR_FLASH_S + 0.01)
    assert rig.led is Color.RED
    assert not rig.machine.command_failed


def test_a_failed_start_while_the_button_is_held_ignores_the_release(rig):
    rig.machine.touch_down()
    rig.complete(0, FAIL)
    rig.scheduler.advance(0.1)
    rig.machine.touch_up()
    assert rig.machine.state is State.IDLE
    assert rig.sent == [Command.START]


def test_a_late_start_failure_does_not_kill_a_newer_recording(rig):
    rig.tap()  # recording #1, its START is still unconfirmed
    rig.machine.touch_down()
    rig.machine.touch_up()  # stop
    rig.scheduler.advance(0.5)
    rig.tap()  # recording #2
    assert rig.machine.state is State.RECORDING_LOCKED
    rig.complete(0, FAIL)  # START #1 finally reports failure
    assert rig.machine.state is State.RECORDING_LOCKED
    assert rig.led is Color.YELLOW  # still flashes: something did fail


def test_a_failed_stop_is_repeated_before_the_next_start(rig):
    rig.tap()
    rig.machine.touch_down()  # stops
    rig.machine.touch_up()
    rig.complete(1, FAIL)
    assert rig.machine.state is State.IDLE
    rig.scheduler.advance(0.5)
    rig.calls.clear()
    rig.machine.touch_down()
    assert rig.sent == [Command.STOP, Command.START]


def test_a_successful_stop_clears_the_pending_repeat(rig):
    rig.machine.wake()  # STOP #0
    rig.complete(0, FAIL)  # now a repeat is owed
    rig.machine.wake()  # STOP #1
    rig.complete(1)  # delivered, so nothing is owed any more
    rig.scheduler.advance(0.5)
    rig.calls.clear()
    rig.machine.touch_down()
    assert rig.sent == [Command.START]


def test_a_stale_stop_success_does_not_clear_a_newer_stop_failure(rig):
    rig.tap()  # START
    rig.machine.touch_down()  # STOP #1 (index 1)
    rig.machine.touch_up()
    rig.scheduler.advance(0.5)
    rig.tap()  # START (index 2)
    rig.machine.touch_down()  # STOP #2 (index 3)
    rig.machine.touch_up()
    rig.complete(3, FAIL)  # the newer stop failed first
    rig.complete(1)  # then an older stop reports success late
    rig.scheduler.advance(0.5)
    rig.calls.clear()
    rig.machine.touch_down()
    assert rig.sent == [Command.STOP, Command.START]


def test_a_stop_failure_after_wispr_quit_is_not_repeated_later(rig):
    rig.tap()
    rig.machine.touch_down()
    rig.machine.touch_up()
    rig.machine.wispr_running_changed(False)
    rig.complete(1, FAIL)
    rig.machine.wispr_running_changed(True)
    rig.scheduler.advance(0.5)
    rig.calls.clear()
    rig.machine.touch_down()
    assert rig.sent == [Command.START]


def test_repeated_failures_keep_the_error_visible_until_a_dispatch_succeeds(rig):
    for _ in range(PERSISTENT_FAILURES):
        rig.machine.wake()
    rig.complete_all(FAIL)
    rig.scheduler.advance(ERROR_FLASH_S + 0.01)
    assert rig.machine.command_failed
    rig.machine.wake()
    rig.complete(len(rig.calls) - 1)
    assert not rig.machine.command_failed


def test_isolated_failures_stop_showing_once_the_flash_ends(rig):
    rig.machine.wake()
    rig.complete(0, FAIL)
    rig.scheduler.advance(ERROR_FLASH_S + 0.01)
    assert not rig.machine.command_failed


def test_a_second_failure_during_the_flash_restarts_it(rig):
    rig.machine.wake()
    rig.machine.wake()
    rig.complete(0, FAIL)
    rig.scheduler.advance(ERROR_FLASH_S - 0.2)
    rig.complete(1, FAIL)
    rig.scheduler.advance(0.5)  # past the first flash's end, within the second's
    assert rig.led is Color.YELLOW
    rig.scheduler.advance(ERROR_FLASH_S)
    assert rig.led is Color.RED


# --- LED priority (spec 5.1) -------------------------------------------------------------


def stale_start_failure(rig):
    """Leave a recording running while an older START reports failure (a flash)."""
    rig.tap()  # recording #1
    rig.machine.touch_down()
    rig.machine.touch_up()  # stop
    rig.scheduler.advance(0.5)
    rig.tap()  # recording #2, still running
    rig.complete(0, FAIL)


def test_an_error_flash_outranks_the_recording_green(rig):
    stale_start_failure(rig)
    assert rig.machine.state is State.RECORDING_LOCKED
    assert rig.led is Color.YELLOW


def test_the_recording_green_returns_when_the_flash_ends(rig):
    stale_start_failure(rig)
    rig.scheduler.advance(ERROR_FLASH_S + 0.01)
    assert rig.led is Color.GREEN


def test_an_error_flash_outranks_the_wispr_away_blue(rig):
    rig.machine.wake()
    rig.complete(0, FAIL)
    rig.machine.wispr_running_changed(False)
    assert rig.led is Color.YELLOW
    rig.scheduler.advance(ERROR_FLASH_S + 0.01)
    assert rig.led is Color.BLUE


def test_a_device_that_cannot_be_opened_outranks_the_wispr_away_blue():
    rig = Rig(wispr_running=False)
    rig.machine.device_open_failed()
    assert rig.led is Color.YELLOW


# --- device and app lifecycle (spec 4.5) ------------------------------------------------


def test_unplugging_mid_recording_stops_wispr(rig):
    rig.tap()
    rig.machine.device_detached()
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE
    assert not rig.machine.device_connected


def test_unplugging_while_idle_sends_nothing(rig):
    rig.machine.device_detached()
    assert rig.sent == []


def test_unplugging_mid_push_to_talk_stops_wispr_once_and_ignores_later_events(rig):
    rig.machine.touch_down()
    rig.scheduler.advance(HOLD + 0.1)
    rig.machine.device_detached()
    rig.machine.device_attached()
    rig.machine.touch_up()
    assert rig.sent == [Command.START, Command.STOP]


def test_reattaching_resends_the_current_led_colour(rig):
    rig.leds.clear()
    rig.machine.device_attached()
    assert rig.leds == [Color.RED]


def test_wake_resyncs_wispr_to_idle(rig):
    rig.tap()
    rig.machine.wake()
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.machine.state is State.IDLE
    assert rig.led is Color.RED


def test_wake_does_not_launch_a_quit_wispr():
    rig = Rig(wispr_running=False)
    rig.machine.wake()
    assert rig.sent == []


def test_a_device_that_cannot_be_opened_shows_yellow_until_it_connects(rig):
    rig.machine.device_open_failed()
    assert rig.machine.open_failed
    assert rig.led is Color.YELLOW
    rig.machine.device_attached()
    assert not rig.machine.open_failed
    assert rig.led is Color.RED


# --- shutdown is terminal -----------------------------------------------------------------


def test_shutdown_stops_a_recording_and_leaves_the_led_red(rig):
    rig.tap()
    rig.machine.shutdown()
    assert rig.sent == [Command.START, Command.STOP]
    assert rig.led is Color.RED
    assert rig.scheduler.pending == 0


def test_shutdown_while_idle_sends_nothing_but_still_sets_red():
    rig = Rig(wispr_running=False)
    rig.machine.shutdown()
    assert rig.sent == []
    assert rig.led is Color.RED


def test_nothing_after_shutdown_can_start_a_recording(rig):
    rig.machine.shutdown()
    rig.calls.clear()
    rig.machine.touch_down()
    rig.machine.touch_up()
    rig.machine.wake()
    rig.machine.wispr_running_changed(False)
    rig.machine.device_attached()
    assert rig.sent == []
    assert rig.led is Color.RED


def test_a_failed_final_stop_does_not_repaint_the_led_after_shutdown(rig):
    rig.tap()
    rig.machine.shutdown()
    rig.complete(len(rig.calls) - 1, FAIL)
    assert rig.led is Color.RED
    assert rig.scheduler.pending == 0


def test_shutdown_twice_is_harmless(rig):
    rig.tap()
    rig.machine.shutdown()
    rig.machine.shutdown()
    assert rig.sent == [Command.START, Command.STOP]
