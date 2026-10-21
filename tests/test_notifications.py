import logging

from support.fake_appkit import FakeNotificationCenter

from limberwisk.notifications import Subscriptions

QUEUE = object()


def test_subscribe_registers_on_the_given_queue_and_delivers_the_notification():
    center = FakeNotificationCenter()
    received = []
    subscriptions = Subscriptions(center, QUEUE)
    subscriptions.subscribe("SomethingHappened", received.append)
    assert center.queues["SomethingHappened"] is QUEUE
    center.post("SomethingHappened", "payload")
    assert received == ["payload"]


def test_subscribe_signal_calls_a_handler_that_ignores_the_payload():
    center = FakeNotificationCenter()
    calls = []
    Subscriptions(center, QUEUE).subscribe_signal("Ping", lambda: calls.append(1))
    center.post("Ping", object())
    assert calls == [1]


def test_several_subscribers_to_one_name_all_hear_it():
    center = FakeNotificationCenter()
    heard = []
    subscriptions = Subscriptions(center, QUEUE)
    subscriptions.subscribe("Same", lambda n: heard.append("first"))
    subscriptions.subscribe("Same", lambda n: heard.append("second"))
    center.post("Same", None)
    assert heard == ["first", "second"]


def test_a_failing_handler_is_logged_not_raised(caplog):
    center = FakeNotificationCenter()

    def boom(_notification):
        raise RuntimeError("handler bug")

    Subscriptions(center, QUEUE).subscribe("X", boom)
    with caplog.at_level(logging.ERROR):
        center.post("X", None)
    assert "handler bug" in caplog.text


def test_unsubscribe_all_removes_every_observer_and_is_repeatable():
    center = FakeNotificationCenter()
    subscriptions = Subscriptions(center, QUEUE)
    subscriptions.subscribe("A", lambda n: None)
    subscriptions.subscribe("B", lambda n: None)
    subscriptions.unsubscribe_all()
    subscriptions.unsubscribe_all()
    assert sorted(center.removed) == ["observer-for-A", "observer-for-B"]
