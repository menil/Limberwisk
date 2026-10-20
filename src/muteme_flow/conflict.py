"""Detects running apps that conflict with the active input source (specs/spec.md section 5)."""

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


def is_conflicting_app(
    name: str,
    bundle_id: str,
    *,
    bundle_ids: frozenset[str] = OFFICIAL_APP_BUNDLE_IDS,
    app_names: frozenset[str] = OFFICIAL_APP_NAMES,
) -> bool:
    """Check if a running application matches any conflicting bundle IDs or process names."""
    if bundle_id == APP_BUNDLE_ID:
        return False  # never mistake ourselves for the app we are avoiding
    has_bundle_match = bool(bundle_id) and bundle_id in bundle_ids
    has_name_match = bool(name) and name in app_names
    return has_bundle_match or has_name_match


def is_official_app(name: str, bundle_id: str) -> bool:
    return is_conflicting_app(
        name, bundle_id, bundle_ids=OFFICIAL_APP_BUNDLE_IDS, app_names=OFFICIAL_APP_NAMES
    )


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
        conflicting_bundle_ids: frozenset[str] = OFFICIAL_APP_BUNDLE_IDS,
        conflicting_app_names: frozenset[str] = OFFICIAL_APP_NAMES,
    ) -> None:
        self._on_change = on_change
        self._list_running = list_running
        self._subscriptions = subscriptions
        self._bundle_ids = conflicting_bundle_ids
        self._app_names = conflicting_app_names
        self._last: bool | None = None

    @classmethod
    def for_current_app(
        cls,
        on_change: Callable[[bool], None],
        *,
        conflicting_bundle_ids: frozenset[str] = OFFICIAL_APP_BUNDLE_IDS,
        conflicting_app_names: frozenset[str] = OFFICIAL_APP_NAMES,
    ) -> "ConflictMonitor":
        from AppKit import NSWorkspace

        return cls(
            on_change,
            list_running=NSWorkspace.sharedWorkspace().runningApplications,
            subscriptions=Subscriptions.for_current_app(),
            conflicting_bundle_ids=conflicting_bundle_ids,
            conflicting_app_names=conflicting_app_names,
        )

    @property
    def conflicting_bundle_ids(self) -> frozenset[str]:
        return self._bundle_ids

    @property
    def conflicting_app_names(self) -> frozenset[str]:
        return self._app_names

    def set_conflicts(
        self,
        bundle_ids: frozenset[str] = frozenset(),
        app_names: frozenset[str] = frozenset(),
    ) -> None:
        """Update conflicting application targets and notify if running status changed."""
        self._bundle_ids = bundle_ids
        self._app_names = app_names
        self._check()

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
        """Return list of active running processes that conflict with the current input source."""
        # Short-circuit: skip process enumeration when active input declares no conflicts
        if not self._bundle_ids and not self._app_names:
            return []
        return [
            app
            for app in self._list_running()
            if not app.isTerminated()
            and is_conflicting_app(
                str(app.localizedName() or ""),
                str(app.bundleIdentifier() or ""),
                bundle_ids=self._bundle_ids,
                app_names=self._app_names,
            )
        ]

    # Canonical alias for general input conflict queries
    conflicting_apps = official_apps

    def _check(self) -> None:
        running = self.running
        if running != self._last:
            self._last = running
            self._on_change(running)
