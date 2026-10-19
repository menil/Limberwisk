import queue
import threading

import pytest
from support import sequences as seq
from support.clock import FakeClock
from support.fake_hid import FakeHidDevice, opened
from support.waiting import DEFAULT_TIMEOUT_S, wait_until

from muteme_flow.devices import MUTEME_ORIGINAL_PID, MUTEME_VID
from muteme_flow.hid_io import DeviceError, DeviceNotFoundError
from muteme_flow.hid_session import WATCHDOG_S
from muteme_flow.hid_worker import DeviceEvent, HidWorker
from muteme_flow.led import Color, LedMailbox, led_report


def quiet_device(*reports):
    """A device that serves `reports`, then stays silent without spinning the CPU."""
    device = FakeHidDevice(read_pause_s=0.001)
    device.feed(*reports)
    return device


class Harness:
    """Runs a HidWorker against scripted fake devices and collects its events."""

    def __init__(self, devices, clock=None):
        self.events: queue.Queue[DeviceEvent] = queue.Queue()
        self.led = LedMailbox()
        self.connects = 0
        self.connect_error: Exception | None = None
        self._devices = list(devices)
        self._lock = threading.Lock()
        kwargs = {"clock": clock} if clock else {}
        self.worker = HidWorker(
            self._connect, self.led, self.events.put, reconnect_interval_s=0.005, **kwargs
        )

    def _connect(self):
        with self._lock:
            self.connects += 1
            if self.connect_error:
                raise self.connect_error
            if not self._devices:
                raise DeviceNotFoundError("nothing plugged in")
            device = self._devices.pop(0)
        device.open(MUTEME_VID, MUTEME_ORIGINAL_PID)
        return device

    def expect(self, *expected):
        got = [self.events.get(timeout=DEFAULT_TIMEOUT_S) for _ in expected]
        assert got == list(expected)

    def plug_in(self, device):
        with self._lock:
            self._devices.append(device)


@pytest.fixture
def start():
    harnesses = []

    def make(*devices, clock=None):
        harness = Harness(devices, clock)
        harnesses.append(harness)
        harness.worker.start()
        return harness

    yield make
    for harness in harnesses:
        harness.worker.stop()
        assert not harness.worker.running, "worker thread leaked"


def test_a_tap_is_reported_as_connect_down_up(start):
    harness = start(quiet_device(*seq.tap()))
    harness.expect(DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP)


def test_unplug_is_reported_and_replug_reconnects(start):
    unplugged = quiet_device(*seq.tap())
    unplugged.disconnect_after(len(seq.tap()))
    harness = start(unplugged, quiet_device(*seq.tap()))
    harness.expect(
        DeviceEvent.CONNECTED,
        DeviceEvent.DOWN,
        DeviceEvent.UP,
        DeviceEvent.DISCONNECTED,
        DeviceEvent.CONNECTED,
        DeviceEvent.DOWN,
        DeviceEvent.UP,
    )


def test_it_keeps_retrying_until_a_device_appears(start):
    harness = start()
    assert wait_until(lambda: harness.connects >= 3)
    harness.plug_in(quiet_device(*seq.tap()))
    harness.expect(DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP)


def test_a_missing_device_is_not_an_event(start):
    harness = start()
    assert wait_until(lambda: harness.connects >= 5)
    assert harness.events.empty()


def test_a_persistent_open_failure_is_reported_once_until_it_clears(start):
    harness = start()
    harness.connect_error = DeviceError("cannot open 0x3603:0x0001: permission denied")
    assert wait_until(lambda: harness.connects >= 6)
    harness.expect(DeviceEvent.OPEN_FAILED)
    assert harness.events.empty()

    harness.connect_error = None
    harness.plug_in(quiet_device())
    harness.expect(DeviceEvent.CONNECTED)


def test_a_different_open_failure_is_reported_again(start):
    harness = start()
    harness.connect_error = DeviceError("permission denied")
    harness.expect(DeviceEvent.OPEN_FAILED)
    harness.connect_error = DeviceError("device busy")
    harness.expect(DeviceEvent.OPEN_FAILED)


def test_silence_past_the_watchdog_is_a_disconnect_and_it_reconnects(start):
    clock = FakeClock()
    harness = start(quiet_device(), quiet_device(*seq.tap()), clock=clock)
    harness.expect(DeviceEvent.CONNECTED)
    clock.advance(WATCHDOG_S + 0.1)
    harness.expect(
        DeviceEvent.DISCONNECTED, DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP
    )


def test_a_failed_led_write_is_a_disconnect(start):
    device = quiet_device()
    harness = start(device)
    harness.expect(DeviceEvent.CONNECTED)
    harness.led.request(Color.GREEN)
    device.disconnect()
    harness.expect(DeviceEvent.DISCONNECTED)


def test_the_requested_led_colour_reaches_the_device(start):
    device = quiet_device()
    harness = start(device)
    harness.led.request(Color.GREEN)
    harness.expect(DeviceEvent.CONNECTED)
    assert wait_until(lambda: device.writes)
    assert device.writes == [led_report(Color.GREEN)]


def test_the_led_colour_is_restored_on_a_replugged_device(start):
    first, second = quiet_device(), quiet_device()
    harness = start(first)
    harness.led.request(Color.YELLOW)
    assert wait_until(lambda: first.writes)

    harness.plug_in(second)
    first.disconnect()
    harness.expect(DeviceEvent.CONNECTED, DeviceEvent.DISCONNECTED, DeviceEvent.CONNECTED)
    assert wait_until(lambda: second.writes)
    assert second.writes == [led_report(Color.YELLOW)]


def test_a_colour_requested_just_before_stop_is_still_written(start):
    device = quiet_device()
    harness = start(device)
    harness.expect(DeviceEvent.CONNECTED)
    harness.led.request(Color.RED)
    harness.worker.stop()
    assert device.writes[-1] == led_report(Color.RED)


def test_all_device_calls_happen_on_the_worker_thread(start):
    device = quiet_device(*seq.tap())
    harness = start(device)
    harness.expect(DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP)
    harness.led.request(Color.RED)
    harness.worker.stop()
    assert len(device.call_threads) == 1
    assert threading.get_ident() not in device.call_threads


def test_pause_releases_the_device_and_resume_reconnects(start):
    first = quiet_device()
    harness = start(first, quiet_device(*seq.tap()))
    harness.expect(DeviceEvent.CONNECTED)

    harness.worker.pause()
    assert not first.is_open  # pause() returns only once the device is released
    harness.expect(DeviceEvent.DISCONNECTED)
    assert wait_until(lambda: False, timeout_s=0.1) is False
    assert harness.connects == 1  # stays released while paused

    harness.worker.resume()
    harness.expect(DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP)


def test_a_bug_while_serving_is_treated_as_a_lost_device(start):
    class Exploding(FakeHidDevice):
        def read(self, size, timeout_ms):
            raise RuntimeError("decoder bug")

    harness = start(Exploding(), quiet_device(*seq.tap()))
    harness.expect(
        DeviceEvent.CONNECTED,
        DeviceEvent.DISCONNECTED,
        DeviceEvent.CONNECTED,
        DeviceEvent.DOWN,
        DeviceEvent.UP,
    )


def test_a_failing_event_handler_does_not_stop_the_worker():
    got_up = threading.Event()
    seen = []

    def faulty_handler(event):
        seen.append(event)
        if event is DeviceEvent.UP:
            got_up.set()
        raise RuntimeError("consumer bug")

    device = opened(quiet_device(*seq.tap()))
    worker = HidWorker(lambda: device, LedMailbox(), faulty_handler)
    worker.start()
    try:
        assert got_up.wait(DEFAULT_TIMEOUT_S)
    finally:
        worker.stop()
    assert seen == [DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP]


def test_an_unexpected_connect_error_does_not_kill_the_thread(start):
    harness = start(quiet_device(*seq.tap()))
    harness.connect_error = ValueError("bug in connect")
    assert wait_until(lambda: harness.connects >= 3)
    harness.connect_error = None
    harness.expect(DeviceEvent.CONNECTED, DeviceEvent.DOWN, DeviceEvent.UP)


def test_stop_closes_the_device_without_reporting_a_disconnect(start):
    device = quiet_device()
    harness = start(device)
    harness.expect(DeviceEvent.CONNECTED)
    harness.worker.stop()
    assert not device.is_open
    assert harness.events.empty()


def test_stop_may_be_called_from_an_event_handler():
    done = threading.Event()
    holder = []

    def stop_on_down(event):
        if event is DeviceEvent.DOWN:
            holder[0].stop()  # runs on the worker thread, so it must not self-join
            done.set()

    device = opened(quiet_device(*seq.tap()))
    worker = HidWorker(lambda: device, LedMailbox(), stop_on_down)
    holder.append(worker)
    worker.start()
    assert done.wait(DEFAULT_TIMEOUT_S)
    assert wait_until(lambda: not worker.running)


def test_start_twice_is_rejected(start):
    harness = start()
    with pytest.raises(RuntimeError):
        harness.worker.start()
