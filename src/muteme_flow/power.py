"""System sleep/wake notifications (specs/spec.md section 4.5)."""

from collections.abc import Callable
from typing import Any

from muteme_flow.guarded import guarded

WILL_SLEEP_NOTIFICATION = "NSWorkspaceWillSleepNotification"
DID_WAKE_NOTIFICATION = "NSWorkspaceDidWakeNotification"


class PowerObserver:
    def __init__(
        self,
        on_sleep: Callable[[], None],
        on_wake: Callable[[], None],
        *,
        notification_center: Any,
        queue: Any,
    ) -> None:
        self._on_sleep = on_sleep
        self._on_wake = on_wake
        self._center = notification_center
        self._queue = queue
        self._observers: list[Any] = []

    @classmethod
    def for_current_app(
        cls, on_sleep: Callable[[], None], on_wake: Callable[[], None]
    ) -> "PowerObserver":
        from AppKit import NSWorkspace
        from Foundation import NSOperationQueue

        return cls(
            on_sleep,
            on_wake,
            notification_center=NSWorkspace.sharedWorkspace().notificationCenter(),
            queue=NSOperationQueue.mainQueue(),
        )

    def start(self) -> None:
        for name, callback in (
            (WILL_SLEEP_NOTIFICATION, self._on_sleep),
            (DID_WAKE_NOTIFICATION, self._on_wake),
        ):
            self._observers.append(
                self._center.addObserverForName_object_queue_usingBlock_(
                    name, None, self._queue, self._ignoring_payload(callback)
                )
            )

    def stop(self) -> None:
        for observer in self._observers:
            self._center.removeObserver_(observer)
        self._observers.clear()

    @staticmethod
    def _ignoring_payload(callback: Callable[[], None]) -> Callable[[Any], None]:
        # Bound per callback here, rather than in the loop, so each observer keeps its own.
        run = guarded(callback, "power notification handler")
        return lambda _notification: run()
