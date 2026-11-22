"""Tracks whether Wispr Flow is running (specs/spec.md section 4.4)."""

import logging
from collections.abc import Callable, Sequence
from typing import Any

from limberwisk.commands import WISPR_BUNDLE_ID
from limberwisk.notifications import TERMINATE_NOTIFICATION, Subscriptions
from limberwisk.running_applications import RunningApplicationsWatch

log = logging.getLogger(__name__)

_APPLICATION_KEY = "NSWorkspaceApplicationKey"

# Named in the log, so that a signal that stops working is visible there.
_STARTUP, _KVO, _TERMINATE = "startup", "kvo", "terminate"


class WisprPresence:
    """One startup check, then live signals: no polling loop.

    Launches come from the running-application list rather than from a launch notification,
    because macOS never posts one for Wispr Flow (see `running_applications`).
    """

    def __init__(
        self,
        on_change: Callable[[bool], None],
        *,
        find_running: Callable[[str], Sequence[Any]],
        subscriptions: Subscriptions,
        watch: RunningApplicationsWatch,
        bundle_id: str = WISPR_BUNDLE_ID,
    ) -> None:
        self._on_change = on_change
        self._find_running = find_running
        self._subscriptions = subscriptions
        self._watch = watch
        self._bundle_id = bundle_id
        self._reported: bool | None = None

    @classmethod
    def for_current_app(
        cls, on_change: Callable[[bool], None], bundle_id: str = WISPR_BUNDLE_ID
    ) -> "WisprPresence":
        from AppKit import NSRunningApplication

        return cls(
            on_change,
            # A class method of NSRunningApplication, not of NSWorkspace.
            find_running=NSRunningApplication.runningApplicationsWithBundleIdentifier_,
            subscriptions=Subscriptions.for_current_app(),
            watch=RunningApplicationsWatch.for_current_app(),
            bundle_id=bundle_id,
        )

    def start(self) -> None:
        # The new owner of the state has not been told anything yet.
        self._reported = None
        # Subscribe before the first check, so a launch in between cannot be missed.
        self._subscriptions.subscribe(TERMINATE_NOTIFICATION, self._handle_terminate)
        self._watch.start(lambda: self._report(_KVO))
        self._report(_STARTUP)

    def stop(self) -> None:
        self._subscriptions.unsubscribe_all()
        self._watch.stop()

    def is_running(self) -> bool:
        """Asked afresh rather than inferred from a signal: a second copy of the app
        quitting must not read as "not running", and a terminating app may still be
        listed for a moment.
        """
        return any(not app.isTerminated() for app in self._find_running(self._bundle_id))

    def _report(self, source: str) -> None:
        """Tell the owner only when the state changed: the running-application list changes
        whenever any app on the Mac starts or quits, and most of those are not ours.
        """
        running = self.is_running()
        if running == self._reported:
            return
        self._reported = running
        log.info(
            "presence of %s: %s (%s)",
            self._bundle_id,
            "running" if running else "not running",
            source,
        )
        self._on_change(running)

    def _handle_terminate(self, notification: Any) -> None:
        app = (notification.userInfo() or {}).get(_APPLICATION_KEY)
        if app is not None and str(app.bundleIdentifier()) == self._bundle_id:
            self._report(_TERMINATE)
