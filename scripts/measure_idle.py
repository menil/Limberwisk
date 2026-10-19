"""Measure the idle memory and CPU of the packaged app (specs/spec.md section 8).

    .venv/bin/python scripts/measure_idle.py "dist/MuteMe Flow.app" --seconds 60

Launches the app, waits for it to settle, then reports resident memory, memory footprint
(what Activity Monitor calls Memory) and average CPU over the window. Nothing touches the
button, so this is the idle figure. With a MuteMe plugged in it is the realistic case;
unplug it to measure the no-device case instead.

It refuses to run if that app is already running, so it can never measure, or quit, a copy
you are using.
"""

import argparse
import contextlib
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

SETTLE_S = 10
LAUNCH_WAIT_S = 10
LAUNCH_POLL_S = 0.5
SAMPLE_INTERVAL_S = 1.0
# Informational goals from specs/spec.md section 8 (never release gates).
MEMORY_GOAL_MB = 50
CPU_GOAL_PERCENT = 0.2


def parse_ps_time(text: str) -> float:
    """Seconds from `ps -o time`, which prints [[d-]h:]m:s.cs (e.g. 1:02.34 or 1-02:03:04)."""
    days = 0.0
    if "-" in text:
        day_part, text = text.split("-", 1)
        days = float(day_part)
    seconds = sum(float(part) * 60**i for i, part in enumerate(reversed(text.split(":"))))
    return days * 86400 + seconds


def parse_footprint_mb(text: str) -> float | None:
    """Megabytes from `footprint` output (e.g. "Footprint: 44 MB"), or None if absent."""
    match = re.search(r"Footprint:\s+([\d.]+)\s+(KB|MB|GB)", text)
    if not match:
        return None
    return float(match.group(1)) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[match.group(2)]


def ps(pid: int, field: str) -> str:
    return subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", f"{field}="], capture_output=True, text=True
    ).stdout.strip()


def running_pids(executable_dir: Path) -> set[int]:
    """Processes whose command line starts with this app's executable folder."""
    listing = subprocess.run(["/bin/ps", "-axo", "pid=,command="], capture_output=True, text=True)
    pids = set()
    for line in listing.stdout.splitlines():
        pid_text, _, command = line.strip().partition(" ")
        if command.startswith(str(executable_dir)):
            pids.add(int(pid_text))
    return pids


def launch(app: Path, executable_dir: Path) -> int | None:
    subprocess.run(["/usr/bin/open", "-n", str(app)], check=True)
    deadline = time.monotonic() + LAUNCH_WAIT_S
    while time.monotonic() < deadline:
        time.sleep(LAUNCH_POLL_S)
        if pids := running_pids(executable_dir):
            return min(pids)
    return None


def sample(pid: int, seconds: int) -> tuple[list[float], float] | None:
    """Resident-memory samples (MB) and average CPU percent, or None if the app exits."""
    cpu_start, wall_start = parse_ps_time(ps(pid, "time")), time.monotonic()
    rss_samples = []
    while time.monotonic() - wall_start < seconds:
        reading = ps(pid, "rss")
        if not reading:
            return None
        rss_samples.append(int(reading) / 1024)
        time.sleep(SAMPLE_INTERVAL_S)
    cpu_seconds = parse_ps_time(ps(pid, "time")) - cpu_start
    return rss_samples, cpu_seconds / (time.monotonic() - wall_start) * 100


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()

    executable_dir = args.app.resolve() / "Contents" / "MacOS"
    if running_pids(executable_dir):
        print(
            "that app is already running; quit it first, so it is not measured or stopped",
            file=sys.stderr,
        )
        return 2
    pid = launch(args.app, executable_dir)
    if pid is None:
        print("the app did not start", file=sys.stderr)
        return 2

    try:
        print(f"pid {pid}; settling for {SETTLE_S} s")
        time.sleep(SETTLE_S)
        result = sample(pid, args.seconds)
        footprint = parse_footprint_mb(
            subprocess.run(
                ["/usr/bin/footprint", "-p", str(pid)], capture_output=True, text=True
            ).stdout
        )
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)  # the app quits in an orderly way on SIGTERM

    if result is None:
        print("the app exited during the measurement", file=sys.stderr)
        return 2
    rss_samples, cpu_percent = result
    average = sum(rss_samples) / len(rss_samples)
    print(f"resident memory: {average:.1f} MB average, {max(rss_samples):.1f} MB peak")
    print(f"footprint:       {f'{footprint:.1f} MB' if footprint else 'unavailable'}")
    print(f"cpu:             {cpu_percent:.3f}% of one core over {args.seconds} s")
    print(f"goals (informational): footprint < {MEMORY_GOAL_MB} MB, cpu < {CPU_GOAL_PERCENT}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
