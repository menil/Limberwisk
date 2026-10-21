"""Keeps exceptions in callbacks from vanishing."""

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


def guarded(fn: Callable[..., Any], what: str) -> Callable[..., None]:
    """Wrap a callback handed to AppKit so a bug in it is logged, not swallowed.

    PyObjC prints exceptions from Objective-C callbacks to stderr, which a bundled
    menu bar app does not have, so without this a failure would be invisible.
    """

    def run(*args: Any) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("error in %s", what)

    return run
