"""Reports changes of `NSWorkspace.runningApplications` (specs/spec.md section 4.4).

This is the launch signal for presence tracking. `NSWorkspaceDidLaunchApplicationNotification`
cannot be used for that: macOS only posts it for apps that are regular at the moment they
finish launching, and Wispr Flow finishes launching as an accessory app and only then
promotes itself, so it never gets one. The list itself does change, and key-value
observation reports it.
"""

import functools
from collections.abc import Callable
from typing import Any

from limberwisk.guarded import guarded
from limberwisk.main_thread import post_to_main

RUNNING_APPLICATIONS_KEY = "runningApplications"

# Nothing is read from the change dictionary: the handler asks again instead, so there is no
# old/new value to request.
_NO_OPTIONS = 0


class RunningApplicationsWatch:
    """Calls a handler on the main thread whenever the set of running applications changes.

    A change is any application on the Mac starting or quitting, so the handler must be
    cheap and must work out for itself whether anything it cares about happened.
    """

    def __init__(
        self,
        workspace: Any,
        *,
        post: Callable[[Callable[[], None]], None],
        make_observer: Callable[[Callable[[], None]], Any],
    ) -> None:
        self._workspace = workspace
        self._post = post
        self._make_observer = make_observer
        self._observer: Any | None = None

    @classmethod
    def for_current_app(cls) -> "RunningApplicationsWatch":
        from AppKit import NSWorkspace

        return cls(
            NSWorkspace.sharedWorkspace(), post=post_to_main, make_observer=_make_system_observer
        )

    def start(self, handler: Callable[[], None]) -> None:
        if self._observer is not None:
            return
        guarded_handler = guarded(handler, "running applications handler")

        def deliver() -> None:
            # A change queued just before stop() must not reach a handler that was stopped,
            # for example the old backend's presence after a backend switch.
            if self._observer is observer:
                guarded_handler()

        # KVO fires on whichever thread changed the list, so hop to the main thread.
        observer = self._make_observer(lambda: self._post(deliver))
        self._observer = observer
        self._workspace.addObserver_forKeyPath_options_context_(
            observer, RUNNING_APPLICATIONS_KEY, _NO_OPTIONS, None
        )

    def stop(self) -> None:
        if self._observer is None:
            return  # removing an observer that was never added raises in Cocoa
        observer, self._observer = self._observer, None
        self._workspace.removeObserver_forKeyPath_(observer, RUNNING_APPLICATIONS_KEY)


@functools.cache
def _observer_class() -> type:
    """Built on first use: it needs PyObjC, and an Objective-C class can only be defined once."""
    import objc
    from Foundation import NSObject

    class RunningApplicationsObserver(NSObject):
        def initWithCallback_(self, callback: Callable[[], None]) -> Any:  # noqa: N802
            self = objc.super(RunningApplicationsObserver, self).init()
            if self is None:
                return None
            self._callback = callback
            return self

        def observeValueForKeyPath_ofObject_change_context_(  # noqa: N802
            self, key_path: str, obj: Any, change: Any, context: Any
        ) -> None:
            self._callback()

    return RunningApplicationsObserver


def _make_system_observer(callback: Callable[[], None]) -> Any:
    return _observer_class().alloc().initWithCallback_(callback)
