"""Tracks whether Wispr Flow is running (specs/spec.md section 4.4)."""

from collections.abc import Callable, Sequence
from typing import Any

from muteme_flow.commands import WISPR_BUNDLE_ID
from muteme_flow.notifications import LAUNCH_NOTIFICATION, TERMINATE_NOTIFICATION, Subscriptions

_APPLICATION_KEY = "NSWorkspaceApplicationKey"


class WisprPresence:
    """One startup check, then launch/terminate notifications: no polling loop."""

    def __init__(
        self,
        on_change: Callable[[bool], None],
        *,
        find_running: Callable[[str], Sequence[Any]],
        subscriptions: Subscriptions,
        bundle_id: str = WISPR_BUNDLE_ID,
    ) -> None:
        self._on_change = on_change
        self._find_running = find_running
        self._subscriptions = subscriptions
        self._bundle_id = bundle_id

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
            bundle_id=bundle_id,
        )

    def start(self) -> None:
        # Subscribe before the first check, so a launch in between cannot be missed.
        self._subscriptions.subscribe(LAUNCH_NOTIFICATION, self._handle)
        self._subscriptions.subscribe(TERMINATE_NOTIFICATION, self._handle)
        self._on_change(self.is_running())

    def stop(self) -> None:
        self._subscriptions.unsubscribe_all()

    def is_running(self) -> bool:
        """Asked afresh rather than inferred from the notification: a second copy of the
        app quitting must not read as "not running", and a terminating app may still be
        listed for a moment.
        """
        return any(not app.isTerminated() for app in self._find_running(self._bundle_id))

    def _is_running(self) -> bool:
        return self.is_running()

    def _handle(self, notification: Any) -> None:
        app = (notification.userInfo() or {}).get(_APPLICATION_KEY)
        if app is not None and str(app.bundleIdentifier()) == self._bundle_id:
            self._on_change(self.is_running())
