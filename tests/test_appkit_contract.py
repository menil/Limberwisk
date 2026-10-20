"""Checks the real AppKit/Foundation API surface the macOS edge modules rely on.

The edge modules are unit-tested with duck-typed fakes, which accept any method name.
That once hid a real bug (`runningApplicationsWithBundleIdentifier:` is a class method
of NSRunningApplication, not NSWorkspace), so these tests pin the genuine API.

They need PyObjC, so they are skipped where it is missing (Linux CI, and the Nix shell's
Python). Run them with the project virtualenv: `.venv/bin/pytest tests/test_appkit_contract.py`.
"""

import pytest

pytest.importorskip("AppKit")


def test_workspace_api_used_for_dispatch():
    from AppKit import NSWorkspace, NSWorkspaceOpenConfiguration

    workspace = NSWorkspace.sharedWorkspace()
    assert hasattr(workspace, "URLForApplicationWithBundleIdentifier_")
    assert hasattr(workspace, "openURLs_withApplicationAtURL_configuration_completionHandler_")
    configuration = NSWorkspaceOpenConfiguration.configuration()
    assert hasattr(configuration, "setActivates_")


def test_running_application_lookup_is_on_nsrunningapplication():
    from AppKit import NSRunningApplication, NSWorkspace

    assert hasattr(NSRunningApplication, "runningApplicationsWithBundleIdentifier_")
    assert not hasattr(NSWorkspace.sharedWorkspace(), "runningApplicationsWithBundleIdentifier_")
    running = NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.apple.finder")
    assert all(hasattr(app, "isTerminated") for app in running)


def test_notification_names_and_payload_key_match_the_system_constants():
    import AppKit

    from muteme_flow import power, wispr_presence

    assert AppKit.NSWorkspaceDidLaunchApplicationNotification == wispr_presence.LAUNCH_NOTIFICATION
    assert (
        AppKit.NSWorkspaceDidTerminateApplicationNotification
        == wispr_presence.TERMINATE_NOTIFICATION
    )
    assert AppKit.NSWorkspaceApplicationKey == wispr_presence._APPLICATION_KEY
    assert AppKit.NSWorkspaceWillSleepNotification == power.WILL_SLEEP_NOTIFICATION
    assert AppKit.NSWorkspaceDidWakeNotification == power.DID_WAKE_NOTIFICATION


def test_notification_center_and_main_queue_api():
    from AppKit import NSWorkspace
    from Foundation import NSOperationQueue

    center = NSWorkspace.sharedWorkspace().notificationCenter()
    assert hasattr(center, "addObserverForName_object_queue_usingBlock_")
    assert hasattr(center, "removeObserver_")
    assert hasattr(NSOperationQueue.mainQueue(), "addOperationWithBlock_")


def test_timer_and_run_loop_api():
    import Foundation

    assert hasattr(Foundation.NSTimer, "timerWithTimeInterval_repeats_block_")
    timer = Foundation.NSTimer.timerWithTimeInterval_repeats_block_(60, False, lambda _t: None)
    assert hasattr(timer, "setTolerance_")
    timer.invalidate()
    assert hasattr(Foundation.NSRunLoop.mainRunLoop(), "addTimer_forMode_")
    assert Foundation.NSRunLoopCommonModes
    assert hasattr(Foundation.NSRunLoop.currentRunLoop(), "runUntilDate_")


def test_service_management_api_for_the_login_item():
    from ServiceManagement import SMAppService

    assert hasattr(SMAppService, "mainAppService")
    service_methods = ("status", "registerAndReturnError_", "unregisterAndReturnError_")
    assert all(hasattr(SMAppService, name) for name in service_methods)


def test_bundle_and_defaults_api():
    from Foundation import NSBundle, NSUserDefaults

    assert hasattr(NSBundle.mainBundle(), "bundleIdentifier")
    assert hasattr(NSBundle, "bundleWithURL_")
    defaults = NSUserDefaults.standardUserDefaults()
    assert all(
        hasattr(defaults, name)
        for name in (
            "objectForKey_",
            "integerForKey_",
            "setInteger_forKey_",
            "setObject_forKey_",
            "boolForKey_",
            "setBool_forKey_",
        )
    )


def test_sound_api_for_audio_feedback():
    from AppKit import NSSound

    assert hasattr(NSSound, "soundNamed_")
    sound = NSSound.soundNamed_("Tink")
    if sound is not None:
        assert hasattr(sound, "play")


def test_pasteboard_and_activation_policy_api():
    import AppKit

    pasteboard = AppKit.NSPasteboard.generalPasteboard()
    assert hasattr(pasteboard, "clearContents")
    assert hasattr(pasteboard, "setString_forType_")
    assert AppKit.NSPasteboardTypeString
    assert hasattr(AppKit.NSApplication.sharedApplication(), "setActivationPolicy_")
    assert AppKit.NSApplicationActivationPolicyAccessory is not None


def test_running_application_api_used_to_detect_and_quit_the_official_app():
    from AppKit import NSWorkspace

    apps = NSWorkspace.sharedWorkspace().runningApplications()
    assert apps
    app = apps[0]
    assert all(
        hasattr(app, name)
        for name in ("localizedName", "bundleIdentifier", "isTerminated", "terminate")
    )


def test_the_sleep_wake_and_terminate_notification_constants_exist():
    import AppKit

    assert AppKit.NSApplicationWillTerminateNotification == "NSApplicationWillTerminateNotification"


def test_service_management_constants_and_settings_link():
    from ServiceManagement import SMAppService, SMAppServiceStatusEnabled

    from muteme_flow import login_item

    assert SMAppServiceStatusEnabled == login_item._STATUS_ENABLED
    assert hasattr(SMAppService, "openSystemSettingsLoginItems")


def test_the_rumps_private_attribute_we_rely_on_to_hide_a_row_exists():
    rumps = pytest.importorskip("rumps")
    assert hasattr(rumps.MenuItem("x")._menuitem, "setHidden_")


def test_rumps_input_device_menu_structure():
    rumps = pytest.importorskip("rumps")
    from muteme_flow.settings import INPUT_DISPLAY_NAMES

    input_menu = rumps.MenuItem("Input Device")
    for name in INPUT_DISPLAY_NAMES.values():
        input_menu.add(rumps.MenuItem(name))

    assert len(input_menu) == len(INPUT_DISPLAY_NAMES)
    assert set(item.title for item in input_menu.values()) == set(INPUT_DISPLAY_NAMES.values())
    assert "MuteMe" in set(INPUT_DISPLAY_NAMES.values())


def test_app_menu_reflects_active_input_and_conflict_title():
    pytest.importorskip("rumps")
    from unittest.mock import MagicMock

    from muteme_flow.app import MuteMeFlowApp
    from muteme_flow.settings import Settings

    class InMemoryStore:
        def __init__(self):
            self.data = {}

        def get_int(self, key):
            return self.data.get(key)

        def set_int(self, key, val):
            self.data[key] = val

        def get_str(self, key):
            return self.data.get(key)

        def set_str(self, key, val):
            self.data[key] = val

        def get_bool(self, key):
            return self.data.get(key)

        def set_bool(self, key, val):
            self.data[key] = val

    runtime = MagicMock()
    runtime.controller.machine.device_connected = True
    runtime.controller.machine.conflict = False
    runtime.controller.machine.command_failed = False
    runtime.controller.machine.open_failed = False
    runtime.controller.machine.wispr_running = True
    runtime.controller.machine.recording = False
    runtime.connected_device_name = "MuteMe"

    settings = Settings(InMemoryStore())
    login_item = MagicMock()
    login_item.available = False
    conflict = MagicMock()
    recent = MagicMock()

    app = MuteMeFlowApp(
        runtime=runtime,
        settings=settings,
        login_item=login_item,
        conflict=conflict,
        recent_lines=recent,
    )

    assert app._device_row.title == "Input: MuteMe (connected)"
    assert app._conflict_row.title == "⚠️ Official MuteMe app is running (click to quit)"
    assert app._input_rows["muteme"].state == 1

    # Dynamic device name and conflict state
    runtime.connected_device_name = "KeySwitch"
    runtime.controller.machine.conflict = True
    app.refresh()
    assert app._conflict_row.title == "⚠️ Official KeySwitch app is running (click to quit)"
    assert app._device_row.title == "Input: KeySwitch (connected)"
