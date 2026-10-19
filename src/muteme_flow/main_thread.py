"""Run a callable on the main thread from any thread."""

from collections.abc import Callable

from muteme_flow.guarded import guarded


def post_to_main(fn: Callable[[], None]) -> None:
    """Queue `fn` on the main thread.

    Uses the main operation queue, which is drained in every run-loop mode, so events
    keep flowing while a menu is open (event-tracking mode). `AppHelper.callAfter` only
    runs in the default mode and would stall then.
    """
    from Foundation import NSOperationQueue

    NSOperationQueue.mainQueue().addOperationWithBlock_(guarded(fn, "main-thread callback"))
