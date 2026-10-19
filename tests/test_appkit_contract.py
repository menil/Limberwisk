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
    assert hasattr(Foundation.NSRunLoop.mainRunLoop(), "addTimer_forMode_")
    assert Foundation.NSRunLoopCommonModes
    assert hasattr(Foundation.NSRunLoop.currentRunLoop(), "runUntilDate_")
