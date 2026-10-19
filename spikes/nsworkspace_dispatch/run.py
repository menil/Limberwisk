"""Spike: do Wispr Flow's hands-free URLs behave as specified via NSWorkspace?

Re-runs the cases from specs/spec.md section 4.2 through the same API the app will
use (`NSWorkspace.openURLs` with `activates=False`) instead of the `open -g` tool, and
checks that the frontmost application never changes. Wispr's recording state cannot
be read programmatically, so the script asks the operator what they saw.

This starts real dictation on the machine it runs on. Run it manually:

    .venv/bin/python spikes/nsworkspace_dispatch/run.py --reps 10

Use --no-prompt to skip the questions and only record completion errors, focus
changes and dispatch latency.

The latency column is the time until LaunchServices reports the URL handed to Wispr.
It excludes the HID read and Wispr's own reaction, so it is a lower bound for the
dispatch leg of the 25 ms touch-to-dispatch goal, not a measurement of the whole goal.
"""

import argparse
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple

from AppKit import NSWorkspace, NSWorkspaceOpenConfiguration
from Foundation import NSURL, NSDate, NSRunLoop

WISPR_BUNDLE_ID = "com.electron.wispr-flow"
START = "wispr-flow://start-hands-free"
STOP = "wispr-flow://stop-hands-free"
COMPLETION_TIMEOUT_S = 5.0
# Gives Wispr time to react between steps.
SETTLE_S = 2.0
# The section 4.2 case where a stop follows a start almost immediately.
RAPID_STOP_DELAY_S = 0.1
LONG_RECORDING_S = 4.0
# Lets any app activation caused by a dispatch land before the frontmost app is sampled.
ACTIVATION_SETTLE_S = 0.2
FOCUS_SELF_TEST_S = 8.0


def pump(seconds: float) -> None:
    """Wait while servicing the run loop.

    A plain `time.sleep` leaves NSWorkspace's cached state stale in a script without a
    running app loop, which would make the focus check pass vacuously.
    """
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))


def frontmost_bundle_id() -> str | None:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return str(app.bundleIdentifier()) if app else None


@dataclass
class Dispatch:
    latency_ms: float
    error: str | None


class Dispatcher:
    def __init__(self) -> None:
        self._workspace = NSWorkspace.sharedWorkspace()
        self._app_url = self._workspace.URLForApplicationWithBundleIdentifier_(WISPR_BUNDLE_ID)
        if self._app_url is None:
            raise RuntimeError("Wispr Flow is not installed")

    def dispatch(self, url: str) -> Dispatch:
        config = NSWorkspaceOpenConfiguration.configuration()
        config.setActivates_(False)

        # One holder per call, so a late completion after a timeout cannot touch a later call.
        result: list[str | None] = []

        def completion(_app, error):
            result.append(str(error) if error else None)

        started = time.perf_counter()
        self._workspace.openURLs_withApplicationAtURL_configuration_completionHandler_(
            [NSURL.URLWithString_(url)], self._app_url, config, completion
        )
        while not result and time.perf_counter() - started < COMPLETION_TIMEOUT_S:
            pump(0.005)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return Dispatch(elapsed_ms, result[0] if result else "completion handler timed out")


@dataclass
class CaseResult:
    name: str
    runs: int = 0
    focus_changes: int = 0
    errors: list[str] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    observed_ok: int | None = None


def run_step(dispatcher: Dispatcher, result: CaseResult, url: str) -> None:
    before = frontmost_bundle_id()
    outcome = dispatcher.dispatch(url)
    pump(ACTIVATION_SETTLE_S)
    if frontmost_bundle_id() != before:
        result.focus_changes += 1
    result.latencies_ms.append(outcome.latency_ms)
    if outcome.error:
        # Name the URL: with start and stop in one case, the bare error does not say which failed.
        result.errors.append(f"{url}: {outcome.error}")


def start_while_recording(d: Dispatcher, r: CaseResult) -> None:
    run_step(d, r, START)
    pump(SETTLE_S)
    run_step(d, r, START)
    pump(SETTLE_S)


def stop_while_idle(d: Dispatcher, r: CaseResult) -> None:
    run_step(d, r, STOP)
    pump(SETTLE_S)


def stop_shortly_after_start(d: Dispatcher, r: CaseResult) -> None:
    run_step(d, r, START)
    pump(RAPID_STOP_DELAY_S)
    run_step(d, r, STOP)
    pump(SETTLE_S)


def start_then_stop_long(d: Dispatcher, r: CaseResult) -> None:
    run_step(d, r, START)
    pump(LONG_RECORDING_S)
    run_step(d, r, STOP)
    pump(SETTLE_S)


class Case(NamedTuple):
    name: str
    steps: Callable[[Dispatcher, CaseResult], None]
    question: str


CASES = [
    Case(
        "start while recording",
        start_while_recording,
        "Recording continued uninterrupted (second start changed nothing)?",
    ),
    Case("stop while idle", stop_while_idle, "Nothing visible happened?"),
    Case(
        "stop ~100ms after start",
        stop_shortly_after_start,
        "Wispr flickered and ended cleanly (no stuck recording)?",
    ),
    Case(
        "4 s recording then stop",
        start_then_stop_long,
        "Say a short sentence during the 4 s: did it transcribe correctly?",
    ),
]


def ask(question: str) -> bool:
    return input(f"  {question} [y/N] ").strip().lower() == "y"


def run_case(dispatcher: Dispatcher, case: Case, reps: int, prompt: bool) -> CaseResult:
    result = CaseResult(case.name)
    for rep in range(1, reps + 1):
        print(f"[{case.name}] run {rep}/{reps}")
        case.steps(dispatcher, result)
        result.runs += 1
        if prompt:
            result.observed_ok = (result.observed_ok or 0) + int(ask(case.question))
        # Leave Wispr idle for the next run. Not recorded: it would skew each case's stats.
        dispatcher.dispatch(STOP)
        pump(SETTLE_S)
    return result


def focus_detector_works() -> bool:
    """Confirm the harness can see a focus change before trusting a result of zero."""
    print(f"Focus self-test: switch to a different application within {FOCUS_SELF_TEST_S:.0f}s...")
    seen = {frontmost_bundle_id()}
    deadline = time.perf_counter() + FOCUS_SELF_TEST_S
    while time.perf_counter() < deadline and len(seen) < 2:
        pump(0.1)
        seen.add(frontmost_bundle_id())
    return len(seen) >= 2


SUMMARY_HEADER = (
    "| Case | Runs | Observed OK | Focus changes | Dispatch errors | Completion ms p50 / max |"
)


def print_summary(results: list[CaseResult]) -> None:
    print(f"\n{SUMMARY_HEADER}")
    print("| :--- | :-: | :-: | :-: | :-: | :-: |")
    for r in results:
        observed = "n/a" if r.observed_ok is None else f"{r.observed_ok}/{r.runs}"
        # Max instead of a high percentile: a handful of samples per case cannot support p95.
        print(
            f"| {r.name} | {r.runs} | {observed} | {r.focus_changes} | {len(r.errors)} "
            f"| {statistics.median(r.latencies_ms):.1f} / {max(r.latencies_ms):.1f} |"
        )
    for r in results:
        for error in r.errors:
            print(f"dispatch error in '{r.name}': {error}")


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--reps", type=positive_int, default=10)
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--skip-focus-self-test", action="store_true")
    args = parser.parse_args()

    try:
        dispatcher = Dispatcher()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    if not args.skip_focus_self_test and not focus_detector_works():
        raise SystemExit("Focus detection saw no change; results would be unreliable.")

    results: list[CaseResult] = []
    try:
        dispatcher.dispatch(STOP)  # warm-up: a no-op when idle, but pays first-call costs
        for case in CASES:
            results.append(run_case(dispatcher, case, args.reps, not args.no_prompt))
    finally:
        # Never leave dictation running if the operator interrupts or the script fails.
        dispatcher.dispatch(STOP)
    print_summary(results)


if __name__ == "__main__":
    main()
