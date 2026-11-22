import logging

from support.fake_appkit import (
    FakeApp,
    FakeNotification,
    FakeNotificationCenter,
    FakeRunningApplicationsWatch,
)

from limberwisk.commands import WISPR_BUNDLE_ID
from limberwisk.notifications import TERMINATE_NOTIFICATION, Subscriptions
from limberwisk.wispr_presence import WisprPresence

MAIN_QUEUE = object()


class Harness:
    def __init__(self, running=False):
        self.center = FakeNotificationCenter()
        self.watch = FakeRunningApplicationsWatch()
        self.changes = []
        self.looked_up = []
        self.running_apps = [FakeApp(WISPR_BUNDLE_ID)] if running else []
        self.presence = WisprPresence(
            self.changes.append,
            find_running=self._find_running,
            subscriptions=Subscriptions(self.center, MAIN_QUEUE),
            watch=self.watch,
        )

    def _find_running(self, bundle_id):
        self.looked_up.append(bundle_id)
        return [app for app in self.running_apps if app._bundle_id == bundle_id]

    def quit(self):
        self.running_apps = []
        self.center.post(TERMINATE_NOTIFICATION, FakeNotification(WISPR_BUNDLE_ID))

    def launch(self):
        """A launch the way Wispr Flow does it: the list changes, no launch notification."""
        self.running_apps = [FakeApp(WISPR_BUNDLE_ID)]
        self.watch.fire()


def make(running=False):
    harness = Harness(running)
    return harness.presence, harness.center, harness.changes


def test_reports_the_initial_state_once_on_start():
    presence, _, changes = make(running=True)
    presence.start()
    assert changes == [True]


def test_reports_not_running_initially_when_wispr_is_absent():
    presence, _, changes = make(running=False)
    presence.start()
    assert changes == [False]


def test_a_launch_that_posts_no_launch_notification_is_still_seen():
    # Wispr Flow finishes launching as an accessory app and only then becomes a regular one,
    # so macOS never posts NSWorkspaceDidLaunchApplicationNotification for it.
    harness = Harness()
    harness.presence.start()
    harness.launch()
    assert harness.changes == [False, True]


def test_an_auto_update_restart_ends_running():
    harness = Harness(running=True)
    harness.presence.start()
    harness.quit()
    harness.launch()
    assert harness.changes == [True, False, True]


def test_quitting_is_seen_through_the_terminate_notification():
    harness = Harness(running=True)
    harness.presence.start()
    harness.quit()
    assert harness.changes == [True, False]


def test_a_second_copy_quitting_does_not_read_as_not_running():
    harness = Harness(running=True)
    harness.presence.start()
    harness.center.post(TERMINATE_NOTIFICATION, FakeNotification(WISPR_BUNDLE_ID))
    assert harness.changes == [True]  # asked afresh: one copy is still there


def test_signals_that_leave_the_state_unchanged_are_not_reported_again():
    # The running-application list changes whenever any app on the Mac starts or quits.
    harness = Harness(running=True)
    harness.presence.start()
    harness.watch.fire()
    harness.watch.fire()
    assert harness.changes == [True]


def test_an_app_that_is_terminating_does_not_count_as_running():
    harness = Harness()
    harness.running_apps = [FakeApp(WISPR_BUNDLE_ID, terminated=True)]
    harness.presence.start()
    harness.watch.fire()
    assert harness.changes == [False]


def test_observers_are_registered_before_the_first_check():
    harness = Harness()
    registered_at_check = []
    original = harness._find_running

    def spying_find(bundle_id):
        registered_at_check.append(
            (sum(len(h) for h in harness.center.handlers.values()), harness.watch.started)
        )
        return original(bundle_id)

    harness.presence._find_running = spying_find
    harness.presence.start()
    assert registered_at_check == [(1, True)]  # so a launch during the check cannot be missed


def test_it_does_not_depend_on_the_launch_notification():
    presence, center, _ = make()
    presence.start()
    assert set(center.handlers) == {TERMINATE_NOTIFICATION}


def test_a_notification_without_user_info_is_ignored_not_fatal():
    harness = Harness()
    harness.presence.start()
    harness.center.post(TERMINATE_NOTIFICATION, FakeNotification(None, no_user_info=True))
    assert harness.changes == [False]
    assert harness.looked_up == [WISPR_BUNDLE_ID]  # only the initial check


def test_other_applications_are_ignored():
    harness = Harness()
    harness.presence.start()
    harness.center.post(TERMINATE_NOTIFICATION, FakeNotification("com.apple.Safari"))
    harness.center.post(TERMINATE_NOTIFICATION, FakeNotification(None))
    assert harness.changes == [False]
    assert harness.looked_up == [WISPR_BUNDLE_ID]  # never re-asked for another app's quit


def test_notifications_are_delivered_on_the_main_queue():
    presence, center, _ = make()
    presence.start()
    assert set(center.queues.values()) == {MAIN_QUEUE}


def test_stop_removes_the_observer_and_stops_the_watch():
    harness = Harness()
    harness.presence.start()
    harness.presence.stop()
    assert harness.center.removed == [f"observer-for-{TERMINATE_NOTIFICATION}"]
    assert not harness.watch.started


def test_a_restarted_presence_reports_its_state_afresh():
    harness = Harness(running=True)
    harness.presence.start()
    harness.presence.stop()
    harness.presence.start()
    assert harness.changes == [True, True]  # the new owner of the state needs the first report


def test_the_initial_check_looks_for_wispr_flows_bundle_id():
    harness = Harness()
    harness.presence.start()
    assert harness.looked_up == [WISPR_BUNDLE_ID]


def test_each_change_is_logged_with_the_signal_that_found_it(caplog):
    harness = Harness()
    with caplog.at_level(logging.INFO, logger="limberwisk.wispr_presence"):
        harness.presence.start()
        harness.launch()
        harness.quit()
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        f"presence of {WISPR_BUNDLE_ID}: not running (startup)",
        f"presence of {WISPR_BUNDLE_ID}: running (kvo)",
        f"presence of {WISPR_BUNDLE_ID}: not running (terminate)",
    ]
