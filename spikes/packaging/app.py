"""Packaging spike: a minimal menu bar app that proves hidapi and rumps bundle.

The title shows how many MuteMe devices hidapi can see, so a launched bundle
demonstrates that the native hid extension was packaged and loads correctly.
"""

import hid
import rumps

MUTEME_VID = 0x3603
MUTEME_PID = 0x0001


def count_devices() -> int:
    return len(hid.enumerate(MUTEME_VID, MUTEME_PID))


class SpikeApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("MuteMe Spike", title=f"MM:{count_devices()}", quit_button="Quit")


if __name__ == "__main__":
    SpikeApp().run()
