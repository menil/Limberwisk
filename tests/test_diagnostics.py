from muteme_flow import __version__
from muteme_flow.devices import KNOWN_DEVICES
from muteme_flow.diagnostics import (
    DiagnosticsInfo,
    describe_device,
    format_diagnostics,
    wispr_version,
)

ORIGINAL = KNOWN_DEVICES[0]
MINI = KNOWN_DEVICES[1]


def info(**overrides):
    values = {
        "app_version": __version__,
        "macos_version": "15.1",
        "wispr_version": "1.6.1174",
        "device": ORIGINAL,
        "status": "Ready (MuteMe connected)",
    }
    return DiagnosticsInfo(**{**values, **overrides})


def test_the_report_names_every_version_the_device_and_the_status():
    text = format_diagnostics(info(), ["line one", "line two"])
    assert f"MuteMe Flow {__version__}" in text
    assert "macOS 15.1" in text
    assert "Wispr Flow 1.6.1174" in text
    assert "Device: MuteMe Original 0x3603:0x0001 (verified)" in text
    assert "Status: Ready (MuteMe connected)" in text
    assert "Status: Status:" not in text


def test_the_recent_log_follows_the_header_in_order():
    text = format_diagnostics(info(), ["first", "second"])
    assert text.index("Recent log:") < text.index("first") < text.index("second")


def test_missing_pieces_are_stated_plainly():
    text = format_diagnostics(info(wispr_version=None, device=None), [])
    assert "Wispr Flow not found" in text
    assert "Device: none connected" in text


def test_unverified_devices_are_labelled_as_such():
    assert "(unverified)" in describe_device(MINI)


class FakeBundle:
    def __init__(self, info):
        self._info = info

    def infoDictionary(self):  # noqa: N802
        return self._info


class FakeWorkspace:
    def __init__(self, url):
        self._url = url

    def URLForApplicationWithBundleIdentifier_(self, _bundle_id):  # noqa: N802
        return self._url


def test_wispr_version_comes_from_the_installed_apps_info_plist():
    version = wispr_version(
        FakeWorkspace("file:///wispr"),
        lambda url: FakeBundle({"CFBundleShortVersionString": "1.6.1174"}),
        "id",
    )
    assert version == "1.6.1174"


def test_wispr_version_is_none_when_not_installed_or_unreadable():
    assert wispr_version(FakeWorkspace(None), lambda url: None, "id") is None
    assert wispr_version(FakeWorkspace("u"), lambda url: None, "id") is None
    assert wispr_version(FakeWorkspace("u"), lambda url: FakeBundle({}), "id") is None
