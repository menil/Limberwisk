"""Tap-to-toggle / hold-to-talk behaviour (specs/spec.md section 4).

Single-threaded by design: every method must be called from the main thread, and all
timing goes through the injected `Scheduler`, so the logic is deterministic under test.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from muteme_flow.commands import Command
from muteme_flow.led import Color
from muteme_flow.scheduler import Scheduler, TimerHandle

log = logging.getLogger(__name__)

ERROR_FLASH_S = 1.0
# Failures in a row after which the menu keeps showing the error until a dispatch works.
PERSISTENT_FAILURES = 3

Completion = Callable[[Exception | None], None]


class State(Enum):
    IDLE = auto()
    PENDING_TOUCH = auto()
    RECORDING_MOMENTARY = auto()  # push-to-talk: held past the hold threshold
    RECORDING_LOCKED = auto()  # hands-free: released before the hold threshold


_RECORDING = (State.PENDING_TOUCH, State.RECORDING_MOMENTARY, State.RECORDING_LOCKED)


@dataclass(frozen=True)
class Timings:
    hold_s: float = 0.350
    debounce_s: float = 0.030


class StateMachine:
    """Decides when to start and stop Wispr Flow and what colour the LED shows.

    `send` hands a command to the dispatcher together with a completion callback that
    must be invoked (on the main thread) once the outcome is known.
    """

    def __init__(
        self,
        *,
        send: Callable[[Command, Completion], None],
        set_led: Callable[[Color], None],
        scheduler: Scheduler,
        timings: Timings | None = None,
    ) -> None:
        self._send = send
        self._set_led = set_led
        self._scheduler = scheduler
        self._timings = timings or Timings()

        self._state = State.IDLE
        self._wispr_running = False
        self._device_connected = False
        self._open_failed = False
        # Once set, the machine ignores everything: the app is quitting and anything that
        # still arrives (a touch, a late completion) must not undo the final stop.
        self._closed = False

        self._touching = False
        # Set when a touch-down was swallowed or already acted on, so its release is not
        # mistaken for a new gesture.
        self._ignore_next_up = False
        self._last_up_at: float | None = None
        self._down_at = 0.0

        # Completions can arrive late and out of order, so each command is numbered and
        # each recording has a generation; a stale result must not act on newer state.
        self._seq = 0
        self._generation = 0
        self._stop_failed_seq = 0
        self._stop_ok_seq = 0
        self._failures = 0

        self._hold_timer: TimerHandle | None = None
        self._flash_timer: TimerHandle | None = None

        self._led_shown: Color | None = None
        self._refresh_led()

    # --- status for the UI -------------------------------------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def wispr_running(self) -> bool:
        return self._wispr_running

    @property
    def device_connected(self) -> bool:
        return self._device_connected

    @property
    def open_failed(self) -> bool:
        return self._open_failed

    @property
    def command_failed(self) -> bool:
        """True while the last dispatch failure should be shown to the user."""
        return self._flash_timer is not None or self._failures >= PERSISTENT_FAILURES

    # --- touch input ----------------------------------------------------------------

    def touch_down(self, at: float | None = None) -> None:
        """`at` is when the HID thread saw the touch; it keeps gesture timing independent
        of how long the event waited for the main thread."""
        now = self._scheduler.now() if at is None else at
        self._touching = True
        if self._closed:
            return

        if self._within_debounce(now) or not self._wispr_running:
            # Swallowed: a bounce, or Wispr is not running and a command would launch it.
            self._ignore_next_up = True
            return

        if self._state is State.IDLE:
            self._begin_recording(now)
        elif self._state is State.RECORDING_LOCKED:
            self._end_recording()
            self._ignore_next_up = True  # the release belongs to the stopping touch

    def touch_up(self, at: float | None = None) -> None:
        now = self._scheduler.now() if at is None else at
        self._touching = False
        self._last_up_at = now
        if self._closed:
            return

        if self._ignore_next_up:
            self._ignore_next_up = False
            return

        if self._state in (State.PENDING_TOUCH, State.RECORDING_MOMENTARY):
            # Judge the gesture by how long the finger was actually down, not by whether
            # the hold timer has run: if the main thread was busy the timer can fire late
            # (or the release be processed late), and the two disagree.
            self._hold_timer = self._cancel(self._hold_timer)
            if now - self._down_at >= self._timings.hold_s:
                self._end_recording()
            else:
                self._state = State.RECORDING_LOCKED

    # --- environment ------------------------------------------------------------------

    def device_attached(self) -> None:
        if self._closed:
            return
        log.info("device attached")
        self._device_connected = True
        self._open_failed = False
        self._forget_touch()
        # A freshly connected device has lost its colour.
        self._refresh_led(force=True)

    def device_detached(self) -> None:
        if self._closed:
            return
        log.info("device detached")
        self._device_connected = False
        self._stop_wispr_if_recording()
        self._abandon_recording()
        self._forget_touch()
        self._last_up_at = None
        self._refresh_led()

    def device_open_failed(self) -> None:
        if self._closed:
            return
        self._open_failed = True
        self._refresh_led()

    def wispr_running_changed(self, running: bool) -> None:
        if self._closed or running == self._wispr_running:
            return
        log.info("Wispr Flow %s", "is running" if running else "is not running")
        self._wispr_running = running
        if not running:
            # No stop is sent: dispatching to a quit Wispr would launch it. Whatever was
            # outstanding no longer matters.
            self._stop_ok_seq = self._stop_failed_seq
            self._abandon_recording()
        self._refresh_led()

    def wake(self) -> None:
        """After system sleep: resync Wispr to idle (specs/spec.md section 4.5)."""
        if self._closed:
            return
        log.info("waking from sleep")
        self._abandon_recording()
        if self._wispr_running:
            self._send_command(Command.STOP)
        self._forget_touch()
        self._refresh_led(force=True)

    def shutdown(self) -> None:
        """App is quitting: stop any recording, leave the LED red, then go inert."""
        if self._closed:
            return
        log.info("shutting down")
        self._stop_wispr_if_recording()
        self._abandon_recording()
        self._flash_timer = self._cancel(self._flash_timer)
        self._set_led(Color.RED)
        self._led_shown = Color.RED
        self._closed = True

    # --- dispatch ---------------------------------------------------------------------

    def _send_command(self, command: Command) -> None:
        self._seq += 1
        seq, generation = self._seq, self._generation
        log.debug("sending %s (#%d)", command.name, seq)
        self._send(command, lambda error: self._dispatch_finished(command, seq, generation, error))

    def _dispatch_finished(
        self, command: Command, seq: int, generation: int, error: Exception | None
    ) -> None:
        if self._closed:
            if error is not None:
                log.error("could not send %s while quitting: %s", command.name, error)
            return

        if error is None:
            self._failures = 0
            if command is Command.STOP:
                self._stop_ok_seq = max(self._stop_ok_seq, seq)
            self._refresh_led()
            return

        self._failures += 1
        log.error("could not send %s to Wispr Flow: %s", command.name, error)
        if command is Command.START:
            # Only the recording this start belonged to is affected; a newer one is fine.
            if generation == self._generation and self._state is not State.IDLE:
                self._abandon_recording()
        elif self._wispr_running:
            # Stopping is still what the user asked for, so the machine is already idle,
            # but the stop is repeated (it is idempotent, section 4.2) before the next
            # start. Pointless if Wispr has since quit.
            self._stop_failed_seq = max(self._stop_failed_seq, seq)
        self._start_flash()

    @property
    def _pending_stop(self) -> bool:
        return self._stop_failed_seq > self._stop_ok_seq

    def _stop_wispr_if_recording(self) -> None:
        if self._state in _RECORDING and self._wispr_running:
            self._send_command(Command.STOP)

    # --- recording --------------------------------------------------------------------

    def _within_debounce(self, now: float) -> bool:
        return self._last_up_at is not None and now - self._last_up_at < self._timings.debounce_s

    def _begin_recording(self, now: float) -> None:
        self._generation += 1
        self._down_at = now
        self._state = State.PENDING_TOUCH
        self._hold_timer = self._scheduler.call_later(self._timings.hold_s, self._hold_elapsed)
        # Light the LED before dispatching: the dispatch is the slow part.
        self._refresh_led()
        if self._pending_stop:
            self._send_command(Command.STOP)
        self._send_command(Command.START)

    def _hold_elapsed(self) -> None:
        self._hold_timer = None
        if not self._closed and self._state is State.PENDING_TOUCH:
            self._state = State.RECORDING_MOMENTARY

    def _end_recording(self) -> None:
        self._hold_timer = self._cancel(self._hold_timer)
        self._state = State.IDLE
        self._refresh_led()
        self._send_command(Command.STOP)

    def _abandon_recording(self) -> None:
        """Return to IDLE without sending anything."""
        self._hold_timer = self._cancel(self._hold_timer)
        if self._touching and self._state in _RECORDING:
            self._ignore_next_up = True
        self._state = State.IDLE

    def _forget_touch(self) -> None:
        self._touching = False
        self._ignore_next_up = False

    @staticmethod
    def _cancel(timer: TimerHandle | None) -> None:
        if timer is not None:
            timer.cancel()
        return None

    # --- LED and error flash ------------------------------------------------------------

    def _start_flash(self) -> None:
        self._cancel(self._flash_timer)
        self._flash_timer = self._scheduler.call_later(ERROR_FLASH_S, self._end_flash)
        self._refresh_led()

    def _end_flash(self) -> None:
        self._flash_timer = None
        if not self._closed:
            self._refresh_led()

    def _wanted_led(self) -> Color:
        if self._flash_timer is not None or self._open_failed:
            return Color.YELLOW
        if not self._wispr_running:
            return Color.BLUE
        if self._state in _RECORDING:
            return Color.GREEN
        return Color.RED

    def _refresh_led(self, *, force: bool = False) -> None:
        wanted = self._wanted_led()
        if force or wanted is not self._led_shown:
            self._led_shown = wanted
            self._set_led(wanted)
