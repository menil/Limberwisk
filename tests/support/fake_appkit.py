"""Duck-typed stand-ins for the few AppKit objects the macOS edge modules touch."""

from typing import Any


class FakeConfiguration:
    def __init__(self) -> None:
        self.activates: bool | None = None

    def setActivates_(self, value: bool) -> None:  # noqa: N802 - mirrors the Cocoa name
        self.activates = value


class FakeWorkspace:
    def __init__(self, installed: bool = True) -> None:
        self.installed = installed
        self.open_error: Exception | None = None
        self.requested_bundle_ids: list[str] = []
        self.opened: list[dict[str, Any]] = []

    def URLForApplicationWithBundleIdentifier_(self, bundle_id: str) -> Any:  # noqa: N802
        self.requested_bundle_ids.append(bundle_id)
        return "file:///Applications/Wispr%20Flow.app" if self.installed else None

    def openURLs_withApplicationAtURL_configuration_completionHandler_(  # noqa: N802
        self, urls: list[Any], app_url: Any, configuration: Any, handler: Any
    ) -> None:
        if self.open_error:
            raise self.open_error
        self.opened.append(
            {"urls": urls, "app_url": app_url, "configuration": configuration, "handler": handler}
        )


class FakeApp:
    def __init__(
        self, bundle_id: str, terminated: bool = False, name: str = "App", accepts_quit: bool = True
    ) -> None:
        self._bundle_id = bundle_id
        self._terminated = terminated
        self._name = name
        self._accepts_quit = accepts_quit
        self.terminate_calls = 0
        self.force_terminate_calls = 0

    def localizedName(self) -> str:  # noqa: N802
        return self._name

    def terminate(self) -> bool:
        self.terminate_calls += 1
        return self._accepts_quit

    def forceTerminate(self) -> bool:  # noqa: N802
        self.force_terminate_calls += 1
        return True

    def isTerminated(self) -> bool:  # noqa: N802
        return self._terminated

    def bundleIdentifier(self) -> str:  # noqa: N802
        return self._bundle_id


class FakeNotification:
    def __init__(self, bundle_id: str | None, *, no_user_info: bool = False) -> None:
        self._info = None if no_user_info else {}
        if bundle_id is not None:
            self._info = {"NSWorkspaceApplicationKey": FakeApp(bundle_id)}

    def userInfo(self) -> dict[str, Any] | None:  # noqa: N802
        return self._info


class FakeNotificationCenter:
    def __init__(self) -> None:
        self.handlers: dict[str, list[Any]] = {}
        self.queues: dict[str, Any] = {}
        self.removed: list[Any] = []

    def addObserverForName_object_queue_usingBlock_(  # noqa: N802
        self, name: str, obj: Any, queue: Any, block: Any
    ) -> Any:
        self.handlers.setdefault(name, []).append(block)
        self.queues[name] = queue
        return f"observer-for-{name}"

    def removeObserver_(self, observer: Any) -> None:  # noqa: N802
        self.removed.append(observer)

    def post(self, name: str, notification: Any = None) -> None:
        for handler in self.handlers[name]:
            handler(notification)
