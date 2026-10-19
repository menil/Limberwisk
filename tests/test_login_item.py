from muteme_flow.app_info import APP_BUNDLE_ID
from muteme_flow.login_item import LoginItem


class FakeService:
    def __init__(self, status=0, succeed=True):
        self._status = status
        self._succeed = succeed
        self.calls = []

    def status(self):
        return self._status

    def registerAndReturnError_(self, _error):  # noqa: N802
        self.calls.append("register")
        return (self._succeed, None if self._succeed else "denied")

    def unregisterAndReturnError_(self, _error):  # noqa: N802
        self.calls.append("unregister")
        return (self._succeed, None if self._succeed else "denied")


def test_unavailable_when_run_from_source():
    # From source the main bundle is the Python interpreter, which must never be registered.
    item = LoginItem(FakeService(), main_bundle_id="org.python.python")
    assert not item.available
    assert not item.is_enabled()


def test_unavailable_without_a_service():
    assert not LoginItem(None, APP_BUNDLE_ID).available


def test_refuses_to_change_anything_when_unavailable():
    service = FakeService()
    error = LoginItem(service, main_bundle_id="org.python.python").set_enabled(True)
    assert error is not None
    assert service.calls == []


def test_available_in_the_installed_app():
    assert LoginItem(FakeService(), APP_BUNDLE_ID).available


def test_reports_the_enabled_status():
    assert LoginItem(FakeService(status=1), APP_BUNDLE_ID).is_enabled()
    assert not LoginItem(FakeService(status=0), APP_BUNDLE_ID).is_enabled()
    assert not LoginItem(FakeService(status=2), APP_BUNDLE_ID).is_enabled()  # needs approval


def test_enabling_and_disabling_call_the_matching_service_method():
    service = FakeService()
    item = LoginItem(service, APP_BUNDLE_ID)
    assert item.set_enabled(True) is None
    assert item.set_enabled(False) is None
    assert service.calls == ["register", "unregister"]


def test_a_failure_is_returned_for_the_caller_to_show():
    error = LoginItem(FakeService(succeed=False), APP_BUNDLE_ID).set_enabled(True)
    assert "denied" in str(error)


def test_a_pending_approval_is_detected_and_not_treated_as_enabled():
    item = LoginItem(FakeService(status=2), APP_BUNDLE_ID)
    assert item.requires_approval()
    assert not item.is_enabled()


def test_no_approval_is_needed_in_other_states():
    assert not LoginItem(FakeService(status=0), APP_BUNDLE_ID).requires_approval()
    assert not LoginItem(FakeService(status=1), APP_BUNDLE_ID).requires_approval()


def test_opening_settings_uses_the_system_service():
    class SettingsOpener:
        opened = 0

        @classmethod
        def openSystemSettingsLoginItems(cls):  # noqa: N802
            cls.opened += 1

    LoginItem(FakeService(status=2), APP_BUNDLE_ID, SettingsOpener).open_settings()
    assert SettingsOpener.opened == 1


def test_opening_settings_without_the_service_class_is_a_no_op():
    LoginItem(None, None).open_settings()
