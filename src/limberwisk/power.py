"""System sleep/wake notifications (specs/spec.md section 4.5)."""

from collections.abc import Callable

from limberwisk.notifications import Subscriptions

WILL_SLEEP_NOTIFICATION = "NSWorkspaceWillSleepNotification"
DID_WAKE_NOTIFICATION = "NSWorkspaceDidWakeNotification"


class PowerObserver:
    def __init__(
        self,
        on_sleep: Callable[[], None],
        on_wake: Callable[[], None],
        *,
        subscriptions: Subscriptions,
    ) -> None:
        self._on_sleep = on_sleep
        self._on_wake = on_wake
        self._subscriptions = subscriptions

    @classmethod
    def for_current_app(
        cls, on_sleep: Callable[[], None], on_wake: Callable[[], None]
    ) -> "PowerObserver":
        return cls(on_sleep, on_wake, subscriptions=Subscriptions.for_current_app())

    def start(self) -> None:
        self._subscriptions.subscribe_signal(WILL_SLEEP_NOTIFICATION, self._on_sleep)
        self._subscriptions.subscribe_signal(DID_WAKE_NOTIFICATION, self._on_wake)

    def stop(self) -> None:
        self._subscriptions.unsubscribe_all()
