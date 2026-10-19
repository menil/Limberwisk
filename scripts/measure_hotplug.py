"""Measure how quickly the app notices a replugged MuteMe (specs/spec.md section 8).

    .venv/bin/python scripts/measure_hotplug.py --cycles 20

Needs a person: when it says so, unplug the button, wait a second, and plug it back in.
For each cycle it reports the time between the operating system first listing the USB
device again (read from `ioreg`, so hidapi is only ever used by the app's own worker) and
the worker reporting it connected, which is the part the app controls. The run passes only
if every cycle was measured and none took longer than the gate.
"""

import argparse
import subprocess
import sys
import threading
import time

from muteme_flow.hid_worker import DeviceEvent, HidWorker
from muteme_flow.hidapi_device import open_first_known, preload_hidapi
from muteme_flow.led import LedMailbox

# From specs/spec.md section 8.
TARGET_S = 1.5
GATE_S = 3.0
POLL_INTERVAL_S = 0.1
# A cycle that never completes is a failure, not something to wait on forever.
CYCLE_TIMEOUT_S = 60.0
# The poller may be one poll behind the worker; allow for that before giving up on a stamp.
STAMP_GRACE_S = 0.5


def usb_device_present() -> bool:
    listing = subprocess.run(
        ["/usr/sbin/ioreg", "-p", "IOUSB", "-w0"], capture_output=True, text=True
    ).stdout
    return "MuteMe" in listing  # the product name the device reports


class ReplugProbe:
    """Pairs each OS-level reappearance with the worker's CONNECTED event."""

    def __init__(self) -> None:
        self.latencies: list[float] = []
        self.skipped = 0
        self.progress = threading.Event()  # set whenever a cycle finishes
        self._lock = threading.Lock()
        self._awaiting = False  # between a disconnect and the matching reconnect
        self._listed_at: float | None = None

    def watch(self, stop: threading.Event) -> None:
        was_present = usb_device_present()
        while not stop.is_set():
            present = usb_device_present()
            with self._lock:
                if present and not was_present and self._awaiting and self._listed_at is None:
                    self._listed_at = time.monotonic()
            was_present = present
            time.sleep(POLL_INTERVAL_S)

    def on_event(self, event: DeviceEvent) -> None:
        if event is DeviceEvent.DISCONNECTED:
            with self._lock:
                self._awaiting, self._listed_at = True, None
        elif event is DeviceEvent.CONNECTED:
            self._finish_cycle(time.monotonic())

    def _finish_cycle(self, connected_at: float) -> None:
        with self._lock:
            if not self._awaiting:
                return  # the initial connection, not a replug
        deadline = time.monotonic() + STAMP_GRACE_S
        while time.monotonic() < deadline:
            with self._lock:
                listed_at = self._listed_at
            if listed_at is not None:
                break
            time.sleep(0.02)
        with self._lock:
            self._awaiting = False
            if self._listed_at is None:
                self.skipped += 1  # connected without the poller ever seeing it vanish
            else:
                # Clamped: the poller can stamp a moment after the worker connects.
                self.latencies.append(max(0.0, connected_at - self._listed_at))
        self.progress.set()


def wait_for_cycles(probe: ReplugProbe, cycles: int) -> None:
    while len(probe.latencies) + probe.skipped < cycles:
        probe.progress.clear()
        if not probe.progress.wait(CYCLE_TIMEOUT_S):
            print(f"no replug within {CYCLE_TIMEOUT_S:.0f} s; stopping", file=sys.stderr)
            return
        if probe.latencies:
            print(f"  replug {len(probe.latencies)}/{cycles}: {probe.latencies[-1] * 1000:.0f} ms")


def report(probe: ReplugProbe, cycles: int) -> int:
    latencies = sorted(probe.latencies)
    if not latencies:
        print("no replugs were measured", file=sys.stderr)
        return 2
    worst, median = latencies[-1], latencies[len(latencies) // 2]
    print(f"{len(latencies)} of {cycles} replugs measured ({probe.skipped} skipped)")
    print(f"  worst {worst * 1000:.0f} ms, median {median * 1000:.0f} ms")
    print(f"  target < {TARGET_S} s: {'met' if worst < TARGET_S else 'NOT met'}")
    complete = len(latencies) == cycles
    passed = complete and worst <= GATE_S
    print(f"  release gate (all {cycles} within {GATE_S} s): {'pass' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=20)
    args = parser.parse_args()

    preload_hidapi()  # on the main thread, before the worker thread touches hidapi
    probe, stop = ReplugProbe(), threading.Event()
    worker = HidWorker(open_first_known, LedMailbox(), probe.on_event)
    threading.Thread(target=probe.watch, args=(stop,), daemon=True).start()
    worker.start()
    print(f"Unplug the button, wait a second, plug it back in. {args.cycles} times.")
    try:
        wait_for_cycles(probe, args.cycles)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.stop()
    return report(probe, args.cycles)


if __name__ == "__main__":
    sys.exit(main())
