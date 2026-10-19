"""Detects the official MuteMe app, which fights over the device (specs/spec.md section 5)."""

import logging
from collections.abc import Callable, Sequence
from typing import Any

from muteme_flow.app_info import APP_BUNDLE_ID
from muteme_flow.notifications import LAUNCH_NOTIFICATION, TERMINATE_NOTIFICATION, Subscriptions

log = logging.getLogger(__name__)

OFFICIAL_APP_NAMES = frozenset({"MuteMe", "MuteMe-Client"})
# The official app's bundle identifiers. None have been confirmed against a real install
# (it is not available on the development machine), so matching falls back to the
# process names above until they are filled in (specs/spec.md section 10).
OFFICIAL_APP_BUNDLE_IDS: frozenset[str] = frozenset()


def is_official_app(name: str, bundle_id: str) -> bool:
    if bundle_id == APP_BUNDLE_ID:
        return False  # never mistake ourselves for the app we are avoiding
    return bundle_id in OFFICIAL_APP_BUNDLE_IDS or name in OFFICIAL_APP_NAMES


def describe_apps(apps: Sequence[Any]) -> str:
    """What the confirmation dialog names, so the user knows exactly what will be quit."""
    return ", ".join(
        sorted(
            f"{app.localizedName()} ({app.bundleIdentifier() or 'no bundle id'})" for app in apps
        )
    )


class ConflictMonitor:
    """One startup check, then launch/terminate notifications: no polling loop."""

    def __init__(
        self,
        on_change: Callable[[bool], None],
        *,
        list_running: Callable[[], Sequence[Any]],
        subscriptions: Subscriptions,
    ) -> None:
        self._on_change = on_change
        self._list_running = list_running
        self._subscriptions = subscriptions
        self._last: bool | None = None

    @classmethod
    def for_current_app(cls, on_change: Callable[[bool], None]) -> "ConflictMonitor":
        from AppKit import NSWorkspace

        return cls(
            on_change,
            list_running=NSWorkspace.sharedWorkspace().runningApplications,
            subscriptions=Subscriptions.for_current_app(),
        )

    @property
    def running(self) -> bool:
        return bool(self.official_apps())

    def start(self) -> None:
        self._subscriptions.subscribe_signal(LAUNCH_NOTIFICATION, self._check)
        self._subscriptions.subscribe_signal(TERMINATE_NOTIFICATION, self._check)
        self._check()

    def stop(self) -> None:
        self._subscriptions.unsubscribe_all()

    def terminate(self, apps: Sequence[Any]) -> None:
        """Ask these apps to quit. A polite request, never a force kill.

        Takes the apps rather than looking them up again, so what is quit is exactly what
        the user was shown and agreed to.
        """
        for app in apps:
            if not app.terminate():
                log.warning("%s did not accept the request to quit", app.localizedName())

    def official_apps(self) -> list[Any]:
        return [
            app
            for app in self._list_running()
            if not app.isTerminated()
            and is_official_app(str(app.localizedName() or ""), str(app.bundleIdentifier() or ""))
        ]

    def _check(self) -> None:
        running = self.running
        if running != self._last:
            self._last = running
            self._on_change(running)
