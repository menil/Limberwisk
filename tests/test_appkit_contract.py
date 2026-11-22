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

    from limberwisk import notifications, power, wispr_presence

    assert AppKit.NSWorkspaceDidLaunchApplicationNotification == notifications.LAUNCH_NOTIFICATION
    assert (
        AppKit.NSWorkspaceDidTerminateApplicationNotification
        == notifications.TERMINATE_NOTIFICATION
    )
    assert AppKit.NSWorkspaceApplicationKey == wispr_presence._APPLICATION_KEY
    assert AppKit.NSWorkspaceWillSleepNotification == power.WILL_SLEEP_NOTIFICATION
    assert AppKit.NSWorkspaceDidWakeNotification == power.DID_WAKE_NOTIFICATION


def test_running_applications_kvo_api_used_to_detect_launches():
    from AppKit import NSWorkspace

    from limberwisk.running_applications import RUNNING_APPLICATIONS_KEY

    workspace = NSWorkspace.sharedWorkspace()
    assert hasattr(workspace, "addObserver_forKeyPath_options_context_")
    assert hasattr(workspace, "removeObserver_forKeyPath_")
    # The key must name a real, observable property of NSWorkspace.
    assert hasattr(workspace, RUNNING_APPLICATIONS_KEY)
    assert workspace.valueForKey_(RUNNING_APPLICATIONS_KEY)


def test_the_real_kvo_observer_is_called_when_an_observed_value_changes():
    from Foundation import NSMutableDictionary

    from limberwisk import running_applications

    calls = []
    observer = running_applications._make_system_observer(lambda: calls.append(1))
    observed = NSMutableDictionary.dictionary()
    observed.addObserver_forKeyPath_options_context_(observer, "key", 0, None)
    observed.setValue_forKey_("changed", "key")
    observed.removeObserver_forKeyPath_(observer, "key")
    assert calls == [1]


def test_the_real_watch_adds_and_removes_its_observer_on_nsworkspace():
    from limberwisk.running_applications import RunningApplicationsWatch

    watch = RunningApplicationsWatch.for_current_app()
    watch.start(lambda: None)
    watch.stop()  # raises NSRangeException if the observer was not registered as expected


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

    from limberwisk import login_item

    assert SMAppServiceStatusEnabled == login_item._STATUS_ENABLED
    assert hasattr(SMAppService, "openSystemSettingsLoginItems")


def test_the_rumps_private_attribute_we_rely_on_to_hide_a_row_exists():
    rumps = pytest.importorskip("rumps")
    assert hasattr(rumps.MenuItem("x")._menuitem, "setHidden_")
