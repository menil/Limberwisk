"""A stand-in for the main thread's run loop that the test itself pumps."""

import queue
import threading
import time
from collections.abc import Callable


class ManualMainLoop:
    def __init__(self) -> None:
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self.thread_id = threading.get_ident()

    def post(self, fn: Callable[[], None]) -> None:
        self._queue.put(fn)

    def run_until(self, predicate: Callable[[], bool], timeout_s: float = 3.0) -> bool:
        """Run posted callables on the calling thread until `predicate` holds."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._drain()
            if predicate():
                return True
            time.sleep(0.002)
        self._drain()
        return predicate()

    def settle(self, seconds: float = 0.05) -> None:
        """Run whatever arrives within a short window; for asserting that nothing happens."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._drain()
            time.sleep(0.002)

    def _drain(self) -> None:
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                return
            fn()
