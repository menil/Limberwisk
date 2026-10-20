"""Delivers hands-free commands to Wispr Flow through LaunchServices."""

from collections.abc import Callable
from typing import Any, Protocol

from muteme_flow.commands import WISPR_BUNDLE_ID, Command

Completion = Callable[[Exception | None], None]


class DispatchError(Exception):
    """The URL could not be handed to Wispr Flow."""


class UrlDispatcher(Protocol):
    def dispatch(self, command: Command, on_complete: Completion) -> None:
        """Send `command`; `on_complete` runs later on the main thread with any error."""


class NSWorkspaceDispatcher:
    """Opens `wispr-flow://` URLs with `NSWorkspace.openURLs` without activating the app.

    Targeting Wispr's bundle directly, rather than letting the system pick a handler,
    avoids the URL going to something else, and `activates=False` keeps focus where it
    was (specs/spec.md sections 2 and 4.2). The per-call lookups cost microseconds, so
    nothing is cached and a moved or updated Wispr is always found.
    """

    def __init__(
        self,
        post_to_main: Callable[[Callable[[], None]], None],
        *,
        workspace: Any,
        make_configuration: Callable[[], Any],
        make_url: Callable[[str], Any],
        bundle_id: str = WISPR_BUNDLE_ID,
        app_name: str = "Wispr Flow",
    ) -> None:
        self._post_to_main = post_to_main
        self._workspace = workspace
        self._make_configuration = make_configuration
        self._make_url = make_url
        self._bundle_id = bundle_id
        self._app_name = app_name

    @classmethod
    def for_current_app(
        cls,
        post_to_main: Callable[[Callable[[], None]], None],
        bundle_id: str = WISPR_BUNDLE_ID,
        app_name: str = "Wispr Flow",
    ) -> "NSWorkspaceDispatcher":
        # Imported here so the module loads where AppKit is unavailable (Linux CI).
        from AppKit import NSWorkspace, NSWorkspaceOpenConfiguration
        from Foundation import NSURL

        return cls(
            post_to_main,
            workspace=NSWorkspace.sharedWorkspace(),
            make_configuration=NSWorkspaceOpenConfiguration.configuration,
            make_url=NSURL.URLWithString_,
            bundle_id=bundle_id,
            app_name=app_name,
        )

    def dispatch(self, command: Command, on_complete: Completion) -> None:
        try:
            self._open(command, on_complete)
        except Exception as error:
            # Report even a synchronous failure through the normal path, so the caller
            # gets the same error handling and is never left waiting for a completion.
            self._complete(on_complete, DispatchError(f"{type(error).__name__}: {error}"))

    def _open(self, command: Command, on_complete: Completion) -> None:
        app_url = self._workspace.URLForApplicationWithBundleIdentifier_(self._bundle_id)
        if app_url is None:
            self._complete(on_complete, DispatchError(f"{self._app_name} is not installed"))
            return

        configuration = self._make_configuration()
        configuration.setActivates_(False)

        def completion_handler(_app: Any, error: Any) -> None:
            # Runs on an arbitrary queue; the state machine lives on the main thread.
            self._complete(on_complete, DispatchError(str(error)) if error else None)

        self._workspace.openURLs_withApplicationAtURL_configuration_completionHandler_(
            [self._make_url(command.url)], app_url, configuration, completion_handler
        )

    def _complete(self, on_complete: Completion, error: Exception | None) -> None:
        self._post_to_main(lambda: on_complete(error))
