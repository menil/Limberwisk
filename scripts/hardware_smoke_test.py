"""Manual smoke test for the device layer, run against a real MuteMe.

    .venv/bin/python scripts/hardware_smoke_test.py            # watch touch events for 20 s
    .venv/bin/python scripts/hardware_smoke_test.py --leds     # cycle every LED colour

Needs the project installed in the virtualenv (`pip install -e .`) and the official
MuteMe app quit. The unit tests cover the logic; this checks the real hidapi adapter.
"""

import argparse
import logging
import time

from limberwisk.hid_worker import DeviceEvent, HidWorker
from limberwisk.hidapi_device import open_first_known, preload_hidapi
from limberwisk.led import Color, LedMailbox

COLOR_HOLD_S = 1.5


def cycle_leds() -> None:
    mailbox = LedMailbox()
    worker = HidWorker(open_first_known, mailbox, lambda event: print(f"  {event.name}"))
    worker.start()
    try:
        for color in (Color.RED, Color.GREEN, Color.YELLOW, Color.BLUE, Color.OFF, Color.RED):
            print(f"LED -> {color.name}")
            mailbox.request(color)
            time.sleep(COLOR_HOLD_S)
    finally:
        worker.stop()


def watch_touches(seconds: float) -> None:
    mailbox = LedMailbox()

    def on_event(event: DeviceEvent) -> None:
        print(f"{time.strftime('%H:%M:%S')}  {event.name}")
        if event is DeviceEvent.DOWN:
            mailbox.request(Color.GREEN)
        elif event is DeviceEvent.UP:
            mailbox.request(Color.RED)

    mailbox.request(Color.RED)
    worker = HidWorker(open_first_known, mailbox, on_event)
    worker.start()
    print(f"Touch the button; unplug and replug it to test hotplug ({seconds:.0f}s)...")
    try:
        time.sleep(seconds)
    finally:
        mailbox.request(Color.RED)  # the worker writes this last colour before it exits
        worker.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--leds", action="store_true", help="cycle every LED colour and exit")
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(message)s")
    preload_hidapi()  # must happen on the main thread, before the worker starts
    if args.leds:
        cycle_leds()
    else:
        watch_touches(args.seconds)


if __name__ == "__main__":
    main()
