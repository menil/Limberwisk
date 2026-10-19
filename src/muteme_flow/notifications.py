"""Subscriptions to NSWorkspace notifications, delivered on a given queue."""

from collections.abc import Callable
from typing import Any

from muteme_flow.guarded import guarded

LAUNCH_NOTIFICATION = "NSWorkspaceDidLaunchApplicationNotification"
TERMINATE_NOTIFICATION = "NSWorkspaceDidTerminateApplicationNotification"


class Subscriptions:
    def __init__(self, center: Any, queue: Any) -> None:
        self._center = center
        # Delivering on the main queue keeps handlers on the main thread.
        self._queue = queue
        self._observers: list[Any] = []

    @classmethod
    def for_current_app(cls) -> "Subscriptions":
        from AppKit import NSWorkspace
        from Foundation import NSOperationQueue

        return cls(NSWorkspace.sharedWorkspace().notificationCenter(), NSOperationQueue.mainQueue())

    def subscribe(self, name: str, handler: Callable[[Any], None]) -> None:
        """`handler` receives the notification; an exception in it is logged, not lost."""
        observer = self._center.addObserverForName_object_queue_usingBlock_(
            name, None, self._queue, guarded(handler, f"{name} handler")
        )
        self._observers.append(observer)

    def subscribe_signal(self, name: str, handler: Callable[[], None]) -> None:
        """Like `subscribe`, for handlers that only care that the notification happened."""
        self.subscribe(name, lambda _notification: handler())

    def unsubscribe_all(self) -> None:
        for observer in self._observers:
            self._center.removeObserver_(observer)
        self._observers.clear()
