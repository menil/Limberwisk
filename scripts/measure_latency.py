"""Measure the software part of touch-to-dispatch latency (specs/spec.md section 8).

    .venv/bin/python scripts/measure_latency.py --taps 100 --holds 10

Everything is real except the button: a synthetic device feeds gestures through the real
HID worker thread, controller, state machine, main run loop and `NSWorkspace` dispatcher.
Every command is sent as the idempotent `stop-hands-free` URL, never `start`, so Wispr
Flow is never made to dictate. It must be running (otherwise sending would launch it), and
a dictation in progress would be ended by the stops.

Two things are timed:
  * touch to dispatch: from the HID thread decoding a touch to the command having been
    handed to LaunchServices. Excluded: USB transfer and the HID read itself (microseconds),
    and Wispr Flow's own reaction. The run fails if the p95 exceeds the release gate.
  * LED latency: from a touch event to the LED write reaching the device. For releases the
    synthetic device then stays silent, the worst case for the read loop; a real device
    sends a report ~15 ms after a release.
"""

import argparse
import queue
import statistics
import sys
import threading
import time

from AppKit import NSRunningApplication
from PyObjCTools import AppHelper

from muteme_flow.commands import WISPR_BUNDLE_ID, Command
from muteme_flow.controller import Controller
from muteme_flow.decoder import IDLE, STATE_INDEX, TOUCH_BEGIN, TOUCH_END, TOUCH_HELD
from muteme_flow.dispatcher import Completion, NSWorkspaceDispatcher, UrlDispatcher
from muteme_flow.hid_worker import HidWorker
from muteme_flow.led import Color, LedMailbox
from muteme_flow.main_thread import post_to_main
from muteme_flow.scheduler import NSTimerScheduler
from muteme_flow.state_machine import Timings

# From specs/spec.md section 8.
TARGET_MS = 25
GATE_P95_MS = 50
TAP_HELD_REPORTS = 7  # about 100 ms at the device's ~70 Hz
HELD_REPORT_INTERVAL_S = 0.014
GAP_BETWEEN_TAPS_S = 0.3
HOLD_S = Timings().hold_s + 0.15  # comfortably a push-to-talk hold
SILENCE_AFTER_RELEASE_S = 0.6  # longer than the idle read timeout, so only a timeout wakes it
SETTLE_S = 0.5


class SyntheticButton:
    """A `HidDevice` whose reports are pushed in from another thread."""

    def __init__(self) -> None:
        self._reports: queue.Queue[list[int]] = queue.Queue()
        self.led_writes: list[tuple[float, int]] = []  # (monotonic time, colour byte)

    def push(self, state_code: int) -> None:
        report = [0] * 8
        report[STATE_INDEX] = state_code
        self._reports.put(report)

    def open(self, vid: int, pid: int) -> None:
        pass

    def read(self, size: int, timeout_ms: int) -> list[int]:
        try:
            return self._reports.get(timeout=timeout_ms / 1000)
        except queue.Empty:
            return []

    def write(self, data: bytes) -> int:
        self.led_writes.append((time.monotonic(), data[1]))
        return len(data)

    def close(self) -> None:
        pass


class StopOnlyDispatcher:
    """Wraps the real dispatcher so no command can start dictation, and counts failures."""

    def __init__(self, real: UrlDispatcher) -> None:
        self._real = real
        self.failures = 0

    def dispatch(self, command: Command, on_complete: Completion) -> None:
        def counted(error: Exception | None) -> None:
            self.failures += error is not None
            on_complete(error)

        # The requested command is ignored on purpose: only the harmless stop is ever sent.
        self._real.dispatch(Command.STOP, counted)


def tap(button: SyntheticButton) -> None:
    button.push(TOUCH_BEGIN)
    for _ in range(TAP_HELD_REPORTS):
        time.sleep(HELD_REPORT_INTERVAL_S)
        button.push(TOUCH_HELD)
    button.push(TOUCH_END)
    button.push(IDLE)
    time.sleep(GAP_BETWEEN_TAPS_S)


def hold(button: SyntheticButton, marks: list[tuple[str, float]]) -> None:
    """A push-to-talk hold; records when it began and when it was released."""
    marks.append(("down", time.monotonic()))
    button.push(TOUCH_BEGIN)
    end = time.monotonic() + HOLD_S
    while time.monotonic() < end:
        time.sleep(HELD_REPORT_INTERVAL_S)
        button.push(TOUCH_HELD)
    marks.append(("up", time.monotonic()))
    button.push(TOUCH_END)
    time.sleep(SILENCE_AFTER_RELEASE_S)  # the device says nothing: only a read timeout wakes it
    button.push(IDLE)
    time.sleep(GAP_BETWEEN_TAPS_S)


def run_gestures(button: SyntheticButton, taps: int, holds: int, marks: list) -> None:
    try:
        for _ in range(taps):
            tap(button)
        for _ in range(holds):
            hold(button, marks)
        time.sleep(SETTLE_S)  # let the last dispatch finish
    finally:
        # Whatever happened, never leave the run loop (and so the script) hanging.
        AppHelper.callAfter(AppHelper.stopEventLoop)


def led_latencies_ms(
    button: SyntheticButton, marks: list[tuple[str, float]], event: str, colour: Color
) -> list[float]:
    """For each `event` mark, the delay until the next write of `colour`."""
    result = []
    for name, at in marks:
        if name != event:
            continue
        later = [t for t, byte in button.led_writes if t > at and byte == colour]
        if later:
            result.append((min(later) - at) * 1000)
    return result


def report(label: str, samples: list[float]) -> None:
    if samples:
        print(f"  {label}: median {statistics.median(samples):.1f} ms, max {max(samples):.1f} ms")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--taps", type=int, default=100)
    parser.add_argument("--holds", type=int, default=10)
    args = parser.parse_args()

    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_(WISPR_BUNDLE_ID):
        print("Wispr Flow is not running; start it first.", file=sys.stderr)
        return 2

    button = SyntheticButton()
    dispatcher = StopOnlyDispatcher(NSWorkspaceDispatcher.for_current_app(post_to_main))
    controller = Controller(
        dispatcher=dispatcher,
        led=(led := LedMailbox()),
        scheduler=NSTimerScheduler.for_current_app(),
        post_to_main=post_to_main,
    )
    controller.wispr_running_changed(True)
    worker = HidWorker(lambda: button, led, controller.on_device_event)
    worker.start()
    marks: list[tuple[str, float]] = []
    threading.Thread(
        target=run_gestures, args=(button, args.taps, args.holds, marks), daemon=True
    ).start()

    AppHelper.runConsoleEventLoop(installInterrupt=False)
    worker.stop()

    summary = controller.latency.summary()
    if summary is None:
        print("no samples were recorded", file=sys.stderr)
        return 2
    print(f"{summary.count} commands dispatched, {dispatcher.failures} failed")
    print("  (the state machine alternates start and stop; all were sent as stop-hands-free)")
    print(
        f"touch to dispatch: p50 {summary.p50_ms:.2f} ms | p95 {summary.p95_ms:.2f} ms"
        f" | max {summary.max_ms:.2f} ms"
    )
    print(f"  target < {TARGET_MS} ms: {'met' if summary.p95_ms < TARGET_MS else 'NOT met'}")
    print("LED latency (informational):")
    report("green after touch-down", led_latencies_ms(button, marks, "down", Color.GREEN))
    report("red after release (device silent)", led_latencies_ms(button, marks, "up", Color.RED))

    passed = summary.p95_ms <= GATE_P95_MS and dispatcher.failures == 0
    verdict = "pass" if passed else "FAIL"
    print(f"release gate (p95 <= {GATE_P95_MS} ms, no failed dispatch): {verdict}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
