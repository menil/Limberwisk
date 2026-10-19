"""Polling helper for conditions driven by another thread."""

import time
from collections.abc import Callable

POLL_S = 0.005
DEFAULT_TIMEOUT_S = 3.0


def wait_until(predicate: Callable[[], bool], timeout_s: float = DEFAULT_TIMEOUT_S) -> bool:
    """Poll for a condition driven by another thread, without a fixed sleep."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(POLL_S)
    return predicate()
