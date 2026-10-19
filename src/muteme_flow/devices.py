"""Known MuteMe USB identifiers (specs/spec.md section 3.1).

Devices are matched against an explicit list of (VID, PID) pairs rather than a
VID x PID cross-product, so an unrelated product from the same vendor is never opened.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

MUTEME_VID = 0x3603
MUTEME_ORIGINAL_PID = 0x0001
LEGACY_VID = 0x20A0


@dataclass(frozen=True)
class DeviceId:
    vid: int
    pid: int
    model: str
    # Only the first entry has been exercised on real hardware; the rest are best-effort.
    verified: bool = False


KNOWN_DEVICES = (
    DeviceId(MUTEME_VID, MUTEME_ORIGINAL_PID, "MuteMe Original", verified=True),
    DeviceId(MUTEME_VID, 0x0002, "MuteMe Mini"),
    DeviceId(MUTEME_VID, 0x0003, "MuteMe Mini"),
    DeviceId(MUTEME_VID, 0x0004, "MuteMe Mini"),
    DeviceId(LEGACY_VID, 0x42DA, "MuteMe Original (legacy)"),
    DeviceId(LEGACY_VID, 0x42DB, "MuteMe Mini (legacy)"),
)

_BY_IDS = {(d.vid, d.pid): d for d in KNOWN_DEVICES}
KNOWN_VIDS = frozenset(d.vid for d in KNOWN_DEVICES)


def lookup(vid: int, pid: int) -> DeviceId | None:
    return _BY_IDS.get((vid, pid))


def first_connected(enumerated: Iterable[Mapping[str, Any]]) -> DeviceId | None:
    """Pick the first known device from a `hid.enumerate()` listing.

    The first match wins; additional devices are ignored in v1 (spec section 5.1).
    """
    for entry in enumerated:
        device = lookup(entry["vendor_id"], entry["product_id"])
        if device is not None:
            return device
    return None
