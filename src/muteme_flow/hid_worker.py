"""Background thread that keeps a MuteMe connected and reports what it does.

All device I/O happens on this thread: the hidapi handle must not be shared across
threads, and AppKit must stay on the main thread (specs/spec.md section 4.6). Consumers
receive `DeviceEvent`s through `on_event`, which is called on this thread, so it must
return quickly: a slow handler stalls reads and can trip the silence watchdog.
"""

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from enum import Enum, auto

from muteme_flow.decoder import Edge
from muteme_flow.hid_io import DeviceError, DeviceNotFoundError, HidDevice
from muteme_flow.hid_session import HidSession
from muteme_flow.led import LedMailbox

log = logging.getLogger(__name__)

# Replug must be noticed within 1.5 s (spec section 8); this is the retry cadence while
# no device is present.
RECONNECT_INTERVAL_S = 0.5
# The loop notices a stop request after at most one 50 ms read, so this only needs to
# cover that plus a final LED write; anything longer means the thread is stuck.
STOP_JOIN_TIMEOUT_S = 2.0
PAUSE_ACK_TIMEOUT_S = 1.0


class DeviceEvent(Enum):
    """What consumers hear about the device.

    Separate from `decoder.Edge`, which only knows about touches: connection state is
    this layer's concern, and the decoder should stay ignorant of it.
    """

    CONNECTED = auto()
    DISCONNECTED = auto()
    # A device is plugged in but cannot be opened (permissions, another app holds it).
    # Emitted once per distinct failure; a later CONNECTED means it resolved.
    OPEN_FAILED = auto()
    DOWN = auto()
    UP = auto()


_EDGE_EVENTS = {Edge.DOWN: DeviceEvent.DOWN, Edge.UP: DeviceEvent.UP}


class HidWorker:
    def __init__(
        self,
        connect: Callable[[], HidDevice],
        led: LedMailbox,
        on_event: Callable[[DeviceEvent], None],
        *,
        clock: Callable[[], float] = time.monotonic,
        reconnect_interval_s: float = RECONNECT_INTERVAL_S,
    ) -> None:
        self._connect = connect
        self._led = led
        self._on_event = on_event
        self._clock = clock
        self._reconnect_interval_s = reconnect_interval_s
        self._stop = threading.Event()
        self._paused = threading.Event()
        # Interrupts the wait between connection attempts for resume() and stop().
        self._wake = threading.Event()
        # Set whenever no device handle is held, so pause() can confirm the release.
        self._released = threading.Event()
        self._released.set()
        self._thread: threading.Thread | None = None
        # The last connect problem already reported, so a persistent one is logged and
        # signalled once instead of on every retry.
        self._connect_problem: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("worker already started")
        self._thread = threading.Thread(target=self._run, name="muteme-hid", daemon=True)
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        # Skip the join if called from an event handler running on the worker itself.
        if self._thread is None or self._thread is threading.current_thread():
            return
        self._thread.join(STOP_JOIN_TIMEOUT_S)
        if self._thread.is_alive():
            log.warning("HID worker did not stop within %.1fs", STOP_JOIN_TIMEOUT_S)

    def pause(self) -> None:
        """Release the device, for example before system sleep.

        Waits briefly for the release so a sleep handler knows the device is free.
        """
        self._paused.set()
        self._wake.set()
        if not self._released.wait(PAUSE_ACK_TIMEOUT_S):
            log.warning("HID device was not released within %.1fs of pause", PAUSE_ACK_TIMEOUT_S)

    def resume(self) -> None:
        """Reconnect after `pause`; consumers see CONNECTED again and can resync."""
        self._paused.clear()
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            device = None if self._paused.is_set() else self._try_connect()
            if device is None:
                self._wake.wait(self._reconnect_interval_s)
                self._wake.clear()
                continue
            if self._stop.is_set() or self._paused.is_set():
                # Stop or pause arrived while connecting; hand the device straight back.
                self._close(device)
                continue
            self._emit(DeviceEvent.CONNECTED)
            self._serve(device)

    def _try_connect(self) -> HidDevice | None:
        try:
            device = self._connect()
        except DeviceNotFoundError:
            self._connect_problem = None  # nothing plugged in: the normal waiting state
            return None
        except DeviceError as error:
            self._report_connect_problem(str(error), emit=True)
            return None
        except Exception as error:
            # A bug in the connect callable must not silently end the thread.
            self._report_connect_problem(f"{type(error).__name__}: {error}", unexpected=True)
            return None
        self._connect_problem = None
        self._released.clear()
        return device

    def _report_connect_problem(
        self, summary: str, *, emit: bool = False, unexpected: bool = False
    ) -> None:
        if summary == self._connect_problem:
            return
        self._connect_problem = summary
        if unexpected:
            log.exception("unexpected error while connecting to the device")
        else:
            log.warning("cannot open the device: %s", summary)
        if emit:
            self._emit(DeviceEvent.OPEN_FAILED)

    def _serve(self, device: HidDevice) -> None:
        stopping = False
        try:
            session = HidSession(device, self._led, self._clock)
            # A new or re-plugged device has lost its colour, so send it again.
            self._led.mark_for_resend()
            while True:
                if self._stop.is_set():
                    stopping = True
                    # Honour a colour requested just before shutdown (spec section 4.5).
                    with contextlib.suppress(DeviceError):
                        session.flush_led()
                    return
                if self._paused.is_set():
                    return
                edge = session.step()
                if edge is not None:
                    self._emit(_EDGE_EVENTS[edge])
        except DeviceError as error:
            log.info("device lost: %s", error)
        except Exception:
            # Treat a bug like a lost device so the thread reconnects instead of dying.
            log.exception("unexpected error while serving the device")
        finally:
            self._close(device)
            # On shutdown the consumer already knows; reporting a disconnect then would
            # only invite a spurious reaction while the app is quitting.
            if not stopping:
                self._emit(DeviceEvent.DISCONNECTED)

    def _close(self, device: HidDevice) -> None:
        try:
            device.close()
        except Exception:
            log.exception("error while closing the device")
        finally:
            self._released.set()

    def _emit(self, event: DeviceEvent) -> None:
        try:
            self._on_event(event)
        except Exception:
            # A faulty consumer must not take the device thread down with it.
            log.exception("device event handler failed for %s", event)
