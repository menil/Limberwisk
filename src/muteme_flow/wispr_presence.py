"""Tracks whether Wispr Flow is running (specs/spec.md section 4.4)."""

from collections.abc import Callable, Sequence
from typing import Any

from muteme_flow.commands import WISPR_BUNDLE_ID
from muteme_flow.guarded import guarded

LAUNCH_NOTIFICATION = "NSWorkspaceDidLaunchApplicationNotification"
TERMINATE_NOTIFICATION = "NSWorkspaceDidTerminateApplicationNotification"
_APPLICATION_KEY = "NSWorkspaceApplicationKey"


class WisprPresence:
    """One startup check, then launch/terminate notifications: no polling loop."""

    def __init__(
        self,
        on_change: Callable[[bool], None],
        *,
        find_running: Callable[[str], Sequence[Any]],
        notification_center: Any,
        queue: Any,
    ) -> None:
        self._on_change = on_change
        self._find_running = find_running
        self._center = notification_center
        # Delivering on the main queue keeps `on_change` on the main thread.
        self._queue = queue
        self._observers: list[Any] = []

    @classmethod
    def for_current_app(cls, on_change: Callable[[bool], None]) -> "WisprPresence":
        from AppKit import NSRunningApplication, NSWorkspace
        from Foundation import NSOperationQueue

        return cls(
            on_change,
            # A class method of NSRunningApplication, not of NSWorkspace.
            find_running=NSRunningApplication.runningApplicationsWithBundleIdentifier_,
            notification_center=NSWorkspace.sharedWorkspace().notificationCenter(),
            queue=NSOperationQueue.mainQueue(),
        )

    def start(self) -> None:
        # Subscribe before the first check, so a launch in between cannot be missed.
        for name in (LAUNCH_NOTIFICATION, TERMINATE_NOTIFICATION):
            self._observers.append(
                self._center.addObserverForName_object_queue_usingBlock_(
                    name, None, self._queue, guarded(self._handle, "Wispr presence handler")
                )
            )
        self._on_change(self._is_running())

    def stop(self) -> None:
        for observer in self._observers:
            self._center.removeObserver_(observer)
        self._observers.clear()

    def _is_running(self) -> bool:
        # Asked afresh rather than inferred from the notification: a second copy of the
        # app quitting must not read as "not running", and a terminating app may still be
        # listed for a moment.
        return any(not app.isTerminated() for app in self._find_running(WISPR_BUNDLE_ID))

    def _handle(self, notification: Any) -> None:
        app = (notification.userInfo() or {}).get(_APPLICATION_KEY)
        if app is not None and str(app.bundleIdentifier()) == WISPR_BUNDLE_ID:
            self._on_change(self._is_running())
