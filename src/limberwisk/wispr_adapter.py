"""Adapter exposing Wispr Flow via the DictationBackend protocol."""

from collections.abc import Callable
from typing import Any

from limberwisk.commands import WISPR_BUNDLE_ID, Command
from limberwisk.dispatcher import NSWorkspaceDispatcher, UrlDispatcher
from limberwisk.protocols import (
    DictationBackend,
    DictationCommand,
    DictationCompletion,
    dictation_command_to_command,
)
from limberwisk.wispr_presence import WisprPresence


class WisprFlowBackend(DictationBackend):
    """Dictation backend adapter for Wispr Flow."""

    def __init__(
        self,
        dispatcher: UrlDispatcher,
        *,
        presence_factory: Callable[[Callable[[bool], None]], Any] | None = None,
        bundle_id: str = WISPR_BUNDLE_ID,
        name: str = "Wispr Flow",
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
        bundle_id: str = WISPR_BUNDLE_ID,
        name: str = "Wispr Flow",
    ) -> "WisprFlowBackend":
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
        self, command: DictationCommand | Command, on_complete: DictationCompletion
    ) -> None:
        legacy_cmd = (
            dictation_command_to_command(command)
            if isinstance(command, DictationCommand)
            else command
        )
        self._dispatcher.dispatch(legacy_cmd, on_complete)

    def is_running(self) -> bool:
        # Check active presence object if available (supports duck-typed test doubles
        # as well as real WisprPresence instances without requiring strict inheritance).
        if self._presence is not None and hasattr(self._presence, "is_running"):
            return bool(self._presence.is_running())
        return self._is_running

    def start_presence_watch(self, on_change: Callable[[bool], None]) -> None:
        if self._presence_factory:

            def _wrapped(running: bool) -> None:
                self._is_running = running
                on_change(running)

            self._presence = self._presence_factory(_wrapped)
            self._presence.start()

    def stop_presence_watch(self) -> None:
        if self._presence:
            self._presence.stop()
            self._presence = None
