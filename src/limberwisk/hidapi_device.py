"""`HidDevice` backed by the hidapi Python bindings (macOS)."""

import contextlib
import sys
import threading
from types import ModuleType
from typing import Any

from limberwisk import devices
from limberwisk.hid_io import DeviceError, DeviceNotFoundError


def _load_hid() -> ModuleType:
    # Imported lazily so the rest of the package (and its tests) work where the native
    # extension is unavailable, such as Linux CI.
    #
    # The first import must happen on the main thread. On macOS the module initialises
    # hidapi's HID manager on the importing thread's run loop, and the interpreter's exit
    # hook then tears it down from the main thread, which crashes the process (SIGTRAP
    # in CFRunLoopRemoveSource). Failing loudly here beats a crash at quit.
    if "hid" not in sys.modules and threading.current_thread() is not threading.main_thread():
        raise RuntimeError(
            "hidapi must first be imported on the main thread; call preload_hidapi() at startup"
        )
    import hid

    return hid


def preload_hidapi() -> None:
    """Import hidapi on the calling (main) thread so worker threads can use it safely."""
    _load_hid()


def _resolve(hid_module: Any) -> Any:
    return hid_module if hid_module is not None else _load_hid()


class HidapiDevice:
    """A `HidDevice` that maps hidapi's OSError/ValueError failures to `DeviceError`."""

    def __init__(self, hid_module: Any = None) -> None:
        self._hid = _resolve(hid_module)
        self._raw: Any = None
        self.device_id: devices.DeviceId | None = None

    def open(self, vid: int, pid: int) -> None:
        raw = self._hid.device()
        try:
            raw.open(vid, pid)
            raw.set_nonblocking(0)
        except (OSError, ValueError) as error:
            # open() may have succeeded before set_nonblocking failed; do not leak the handle.
            with contextlib.suppress(OSError, ValueError):
                raw.close()
            raise DeviceError(f"cannot open {vid:#06x}:{pid:#06x}: {error}") from error
        self._raw = raw
        self.device_id = devices.lookup(vid, pid)

    def read(self, size: int, timeout_ms: int) -> list[int]:
        raw = self._require_open()
        try:
            return list(raw.read(size, timeout_ms))
        except (OSError, ValueError) as error:
            raise DeviceError(f"read failed: {error}") from error

    def write(self, data: bytes) -> int:
        raw = self._require_open()
        try:
            written = raw.write(data)
        except (OSError, ValueError) as error:
            raise DeviceError(f"write failed: {error}") from error
        # hidapi reports some failures as -1 rather than raising; a short write would
        # leave the LED in an unknown state, so treat it as a failure too.
        if written < len(data):
            raise DeviceError(f"write failed ({written} of {len(data)} bytes)")
        return written

    def close(self) -> None:
        raw, self._raw = self._raw, None
        if raw is None:
            return
        # The device may already be gone; there is nothing left to release.
        with contextlib.suppress(OSError, ValueError):
            raw.close()

    def _require_open(self) -> Any:
        if self._raw is None:
            raise DeviceError("device not open")
        return self._raw


def _enumerate_known(hid: Any) -> list[dict[str, Any]]:
    # Listing every HID device is several times costlier in CPU than asking for each
    # known vendor, and this runs twice a second while no device is plugged in
    # (idle CPU goal in spec section 8).
    listing: list[dict[str, Any]] = []
    for vid in sorted(devices.KNOWN_VIDS):
        listing.extend(hid.enumerate(vid, 0))
    return listing


def open_first_known(hid_module: Any = None) -> HidapiDevice:
    """Open the first connected known MuteMe, or raise DeviceError if there is none."""
    hid = _resolve(hid_module)
    found = devices.first_connected(_enumerate_known(hid))
    if found is None:
        raise DeviceNotFoundError("no MuteMe device connected")
    device = HidapiDevice(hid)
    device.open(found.vid, found.pid)
    return device
