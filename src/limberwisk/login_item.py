"""Start at Login, through SMAppService (macOS 13+, specs/spec.md section 6)."""

from typing import Any

from limberwisk.app_info import APP_BUNDLE_ID

# SMAppServiceStatus values
_STATUS_ENABLED = 1
_STATUS_REQUIRES_APPROVAL = 2


class LoginItem:
    def __init__(
        self, service: Any, main_bundle_id: str | None, sm_app_service: Any = None
    ) -> None:
        self._service = service
        self._main_bundle_id = main_bundle_id
        self._sm_app_service = sm_app_service

    @classmethod
    def for_current_app(cls) -> "LoginItem":
        from Foundation import NSBundle

        try:
            from ServiceManagement import SMAppService
        except ImportError:
            # Older macOS, or the framework wrapper is missing: the rest of the app
            # should still run, just without this one feature.
            return cls(None, None)
        return cls(
            SMAppService.mainAppService(), NSBundle.mainBundle().bundleIdentifier(), SMAppService
        )

    @property
    def available(self) -> bool:
        """Only the packaged app may register itself.

        From source, the "main app" is the Python interpreter, and registering that
        would add a login item the user did not ask for.
        """
        return self._service is not None and self._main_bundle_id == APP_BUNDLE_ID

    def is_enabled(self) -> bool:
        return self.available and self._service.status() == _STATUS_ENABLED

    def requires_approval(self) -> bool:
        """Registered, but waiting for the user to allow it in System Settings."""
        return self.available and self._service.status() == _STATUS_REQUIRES_APPROVAL

    def open_settings(self) -> None:
        """Take the user to where they can approve the login item."""
        if self._sm_app_service is not None:
            self._sm_app_service.openSystemSettingsLoginItems()

    def set_enabled(self, enabled: bool) -> Exception | None:
        """Returns the error, if any, so the caller can show it."""
        if not self.available:
            return RuntimeError("Start at Login is only available in the installed app")
        action = (
            self._service.registerAndReturnError_
            if enabled
            else self._service.unregisterAndReturnError_
        )
        ok, error = action(None)
        return None if ok else RuntimeError(str(error))
