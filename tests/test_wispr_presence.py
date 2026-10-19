from support.fake_appkit import FakeApp, FakeNotification, FakeNotificationCenter

from muteme_flow.commands import WISPR_BUNDLE_ID
from muteme_flow.notifications import Subscriptions
from muteme_flow.wispr_presence import LAUNCH_NOTIFICATION, TERMINATE_NOTIFICATION, WisprPresence

MAIN_QUEUE = object()


class Harness:
    def __init__(self, running=False):
        self.center = FakeNotificationCenter()
        self.changes = []
        self.looked_up = []
        self.running_apps = [FakeApp(WISPR_BUNDLE_ID)] if running else []
        self.presence = WisprPresence(
            self.changes.append,
            find_running=self._find_running,
            subscriptions=Subscriptions(self.center, MAIN_QUEUE),
        )

    def _find_running(self, bundle_id):
        self.looked_up.append(bundle_id)
        return [app for app in self.running_apps if app._bundle_id == bundle_id]


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


def test_launch_and_terminate_notifications_update_the_state():
    harness = Harness()
    harness.presence.start()
    harness.running_apps = [FakeApp(WISPR_BUNDLE_ID)]
    harness.center.post(LAUNCH_NOTIFICATION, FakeNotification(WISPR_BUNDLE_ID))
    harness.running_apps = []
    harness.center.post(TERMINATE_NOTIFICATION, FakeNotification(WISPR_BUNDLE_ID))
    assert harness.changes == [False, True, False]


def test_a_second_copy_quitting_does_not_read_as_not_running():
    harness = Harness(running=True)
    harness.presence.start()
    harness.center.post(TERMINATE_NOTIFICATION, FakeNotification(WISPR_BUNDLE_ID))
    assert harness.changes == [True, True]  # asked afresh: one copy is still there


def test_an_app_that_is_terminating_does_not_count_as_running():
    harness = Harness()
    harness.running_apps = [FakeApp(WISPR_BUNDLE_ID, terminated=True)]
    harness.presence.start()
    assert harness.changes == [False]


def test_observers_are_registered_before_the_first_check():
    harness = Harness()
    registered_at_check = []
    original = harness._find_running

    def spying_find(bundle_id):
        registered_at_check.append(sum(len(h) for h in harness.center.handlers.values()))
        return original(bundle_id)

    harness.presence._find_running = spying_find
    harness.presence.start()
    assert registered_at_check == [2]  # so a launch during the check cannot be missed


def test_a_notification_without_user_info_is_ignored_not_fatal():
    harness = Harness()
    harness.presence.start()
    harness.center.post(LAUNCH_NOTIFICATION, FakeNotification(None, no_user_info=True))
    assert harness.changes == [False]


def test_other_applications_are_ignored():
    presence, center, changes = make()
    presence.start()
    center.post(LAUNCH_NOTIFICATION, FakeNotification("com.apple.Safari"))
    center.post(TERMINATE_NOTIFICATION, FakeNotification("com.apple.Safari"))
    center.post(LAUNCH_NOTIFICATION, FakeNotification(None))
    assert changes == [False]


def test_notifications_are_delivered_on_the_main_queue():
    presence, center, _ = make()
    presence.start()
    assert set(center.queues.values()) == {MAIN_QUEUE}


def test_stop_removes_every_observer():
    presence, center, _ = make()
    presence.start()
    presence.stop()
    assert sorted(center.removed) == sorted(
        [f"observer-for-{LAUNCH_NOTIFICATION}", f"observer-for-{TERMINATE_NOTIFICATION}"]
    )


def test_the_initial_check_looks_for_wispr_flows_bundle_id():
    harness = Harness()
    harness.presence.start()
    assert harness.looked_up == [WISPR_BUNDLE_ID]
