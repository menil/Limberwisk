from support.fake_appkit import FakeNotificationCenter

from muteme_flow.notifications import Subscriptions
from muteme_flow.power import DID_WAKE_NOTIFICATION, WILL_SLEEP_NOTIFICATION, PowerObserver

MAIN_QUEUE = object()


def make():
    center = FakeNotificationCenter()
    calls = []
    observer = PowerObserver(
        lambda: calls.append("sleep"),
        lambda: calls.append("wake"),
        subscriptions=Subscriptions(center, MAIN_QUEUE),
    )
    return observer, center, calls


def test_sleep_and_wake_notifications_reach_their_own_callbacks():
    observer, center, calls = make()
    observer.start()
    center.post(WILL_SLEEP_NOTIFICATION)
    center.post(DID_WAKE_NOTIFICATION)
    assert calls == ["sleep", "wake"]


def test_stop_removes_both_observers():
    observer, center, _ = make()
    observer.start()
    observer.stop()
    assert len(center.removed) == 2


def test_notifications_are_delivered_on_the_main_queue():
    observer, center, _ = make()
    observer.start()
    assert set(center.queues.values()) == {MAIN_QUEUE}
