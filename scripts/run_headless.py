"""Run the bridge without a menu bar item, for end-to-end testing on real hardware.

    .venv/bin/python scripts/run_headless.py

Needs the project installed (`pip install -e .`), a MuteMe plugged in, Wispr Flow
running, and the official MuteMe app quit. Tap or hold the button; press Ctrl-C to quit.
"""

import logging

from PyObjCTools import AppHelper

from muteme_flow.runtime import Runtime


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(message)s")
    runtime = Runtime.create_default()
    runtime.start()
    try:
        AppHelper.runConsoleEventLoop(installInterrupt=True)
    finally:
        runtime.stop()
        summary = runtime.controller.latency.summary()
        if summary:
            print(
                f"touch-to-dispatch latency over {summary.count} commands (ms): "
                f"p50 {summary.p50_ms:.1f}, p95 {summary.p95_ms:.1f}, max {summary.max_ms:.1f}"
            )


if __name__ == "__main__":
    main()
