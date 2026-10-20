import pytest
from support.fake_appkit import FakeApp, FakeNotificationCenter

from muteme_flow import conflict as conflict_module
from muteme_flow.app_info import APP_BUNDLE_ID
from muteme_flow.conflict import ConflictMonitor, describe_apps, is_official_app
from muteme_flow.notifications import (
    LAUNCH_NOTIFICATION,
    TERMINATE_NOTIFICATION,
    Subscriptions,
)


def official(**kwargs):
    return FakeApp("com.example.official", name="MuteMe", **kwargs)


class Harness:
    def __init__(self, apps=()):
        self.apps = list(apps)
        self.center = FakeNotificationCenter()
        self.changes = []
        self.monitor = ConflictMonitor(
            self.changes.append,
            list_running=lambda: list(self.apps),
            subscriptions=Subscriptions(self.center, None),
        )


@pytest.mark.parametrize(
    ("name", "expected"),
    [("MuteMe", True), ("MuteMe-Client", True), ("MuteMe Flow", False), ("Safari", False)],
)
def test_the_official_app_is_recognised_by_its_process_name(name, expected):
    assert is_official_app(name, "") is expected


def test_a_confirmed_bundle_identifier_matches_whatever_the_name(monkeypatch):
    monkeypatch.setattr(conflict_module, "OFFICIAL_APP_BUNDLE_IDS", frozenset({"com.muteme.app"}))
    assert is_official_app("Something Else", "com.muteme.app")


def test_our_own_app_is_never_mistaken_for_the_official_one():
    assert not is_official_app("MuteMe Flow", APP_BUNDLE_ID)
    assert not is_official_app("MuteMe", APP_BUNDLE_ID)  # even if the names ever collided


def test_reports_the_initial_state_on_start():
    harness = Harness([official()])
    harness.monitor.start()
    assert harness.changes == [True]
    assert harness.monitor.running


def test_launch_and_quit_notifications_update_the_state():
    harness = Harness()
    harness.monitor.start()
    harness.apps.append(official())
    harness.center.post(LAUNCH_NOTIFICATION, None)
    harness.apps.clear()
    harness.center.post(TERMINATE_NOTIFICATION, None)
    assert harness.changes == [False, True, False]


def test_unrelated_launches_do_not_repeat_the_report():
    harness = Harness()
    harness.monitor.start()
    harness.apps.append(FakeApp("com.apple.Safari", name="Safari"))
    harness.center.post(LAUNCH_NOTIFICATION, None)
    assert harness.changes == [False]


def test_an_app_that_is_terminating_does_not_count():
    harness = Harness([official(terminated=True)])
    harness.monitor.start()
    assert harness.changes == [False]


def test_terminate_asks_politely_and_only_the_apps_it_was_given():
    target, bystander = official(), FakeApp("com.apple.Safari", name="Safari")
    harness = Harness([target, bystander])
    harness.monitor.terminate(harness.monitor.official_apps())
    assert target.terminate_calls == 1
    assert target.force_terminate_calls == 0
    assert bystander.terminate_calls == 0


def test_terminate_acts_on_what_was_shown_not_on_a_fresh_lookup():
    shown = official()
    harness = Harness([shown])
    snapshot = harness.monitor.official_apps()
    replacement = official()  # a different process appears while the dialog is open
    harness.apps[:] = [replacement]
    harness.monitor.terminate(snapshot)
    assert shown.terminate_calls == 1
    assert replacement.terminate_calls == 0


def test_an_app_that_declines_to_quit_is_logged(caplog):
    declining = official(accepts_quit=False)
    Harness([declining]).monitor.terminate([declining])
    assert "did not accept" in caplog.text


def test_the_dialog_text_names_each_app_and_its_bundle_id():
    text = describe_apps([official(), FakeApp("", name="MuteMe-Client")])
    assert "MuteMe (com.example.official)" in text
    assert "MuteMe-Client (no bundle id)" in text


def test_stop_removes_the_observers():
    harness = Harness()
    harness.monitor.start()
    harness.monitor.stop()
    assert len(harness.center.removed) == 2


def test_set_conflicts_clears_conflict_when_target_becomes_empty():
    harness = Harness([official()])
    harness.monitor.start()
    assert harness.changes == [True]
    assert harness.monitor.running

    # Switch to an input source with no conflicts
    harness.monitor.set_conflicts(bundle_ids=frozenset(), app_names=frozenset())
    assert harness.changes == [True, False]
    assert not harness.monitor.running
    assert harness.monitor.official_apps() == []


def test_set_conflicts_updates_conflict_detection():
    custom_app = FakeApp("com.vendor.pedalapp", name="PedalApp")
    harness = Harness([custom_app])
    harness.monitor.start()
    # Initially watching MuteMe apps, custom_app is not a conflict
    assert harness.changes == [False]
    assert not harness.monitor.running

    # Switch to input source that conflicts with PedalApp
    harness.monitor.set_conflicts(
        bundle_ids=frozenset({"com.vendor.pedalapp"}),
        app_names=frozenset({"PedalApp"}),
    )
    assert harness.changes == [False, True]
    assert harness.monitor.running
    assert harness.monitor.official_apps() == [custom_app]
