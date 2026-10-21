"""Adapter exposing EnviousWispr via the DictationBackend protocol."""

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

from limberwisk.dispatcher import NSWorkspaceDispatcher, UrlDispatcher
from limberwisk.protocols import (
    DictationBackend,
    DictationCommand,
    DictationCompletion,
)
from limberwisk.wispr_presence import WisprPresence

log = logging.getLogger(__name__)

ENVIOUS_WISPR_BUNDLE_ID = "com.enviouswispr.app"


class EnviousWisprCommand(Enum):
    """Deep-link command URLs recognized by EnviousWispr."""

    START = "envious-wispr://start-dictation"
    STOP = "envious-wispr://stop-dictation"

    @property
    def url(self) -> str:
        """Deep-link command URL string.

        Preserves duck-typing compatibility with limberwisk.commands.Command.
        """
        return self.value


class EnviousWisprBackend(DictationBackend):
    """Dictation backend adapter for EnviousWispr."""

    def __init__(
        self,
        dispatcher: UrlDispatcher,
        *,
        presence_factory: Callable[[Callable[[bool], None]], Any] | None = None,
        bundle_id: str = ENVIOUS_WISPR_BUNDLE_ID,
        name: str = "EnviousWispr",
    ) -> None:
        self._dispatcher = dispatcher
        self._presence_factory = presence_factory
        self._bundle_id = bundle_id
        self._name = name
        self._presence: Any | None = None
        self._is_running = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def bundle_id(self) -> str:
        return self._bundle_id

    @property
    def dispatcher(self) -> UrlDispatcher:
        return self._dispatcher

    @property
    def presence(self) -> Any | None:
        return self._presence

    @classmethod
    def for_current_app(
        cls,
        post_to_main: Callable[[Callable[[], None]], None],
        *,
        bundle_id: str = ENVIOUS_WISPR_BUNDLE_ID,
        name: str = "EnviousWispr",
    ) -> "EnviousWisprBackend":
        """Factory for the production runtime using LaunchServices and system presence."""
        dispatcher = NSWorkspaceDispatcher.for_current_app(
            post_to_main, bundle_id=bundle_id, app_name=name
        )
        return cls(
            dispatcher=dispatcher,
            presence_factory=lambda on_change: WisprPresence.for_current_app(
                on_change, bundle_id=bundle_id
            ),
            bundle_id=bundle_id,
            name=name,
        )

    def dispatch(
        self, command: DictationCommand | EnviousWisprCommand, on_complete: DictationCompletion
    ) -> None:
        """Translate generic or vendor commands to deep-links and dispatch them asynchronously."""
        if isinstance(command, DictationCommand):
            cmd = (
                EnviousWisprCommand.START
                if command == DictationCommand.START
                else EnviousWisprCommand.STOP
            )
        elif isinstance(command, EnviousWisprCommand):
            cmd = command
        else:
            raise ValueError(f"Expected DictationCommand or EnviousWisprCommand, got: {command!r}")

        self._dispatcher.dispatch(cmd, on_complete)

    def is_running(self) -> bool:
        """Check if EnviousWispr is currently running."""
        # Check active presence object if available (supports duck-typed test doubles
        # as well as real WisprPresence instances without requiring strict inheritance).
        if self._presence is not None and hasattr(self._presence, "is_running"):
            return self._presence.is_running()
        if self._presence_factory is not None:
            try:
                from AppKit import NSRunningApplication

                running = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
                    self._bundle_id
                )
                return any(not app.isTerminated() for app in running)
            except (ImportError, AttributeError):
                pass
            except Exception:
                log.exception("unexpected error querying EnviousWispr application presence")
        return self._is_running

    def start_presence_watch(self, on_change: Callable[[bool], None]) -> None:
        """Start monitoring EnviousWispr process presence."""
        if self._presence_factory:
            if self._presence:
                self.stop_presence_watch()

            def _wrapped(running: bool) -> None:
                self._is_running = running
                on_change(running)

            self._presence = self._presence_factory(_wrapped)
            self._presence.start()

    def stop_presence_watch(self) -> None:
        """Stop monitoring EnviousWispr process presence."""
        if self._presence:
            self._presence.stop()
            self._presence = None
            self._is_running = False
