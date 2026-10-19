import pytest
from support import sequences as seq
from support.clock import FakeClock
from support.fake_hid import FakeHidDevice, opened

from muteme_flow.decoder import Edge
from muteme_flow.hid_io import DeviceError
from muteme_flow.hid_session import WATCHDOG_S, HidSession
from muteme_flow.led import Color, LedMailbox, led_report


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def led():
    return LedMailbox()


@pytest.fixture
def session(fake_device, led, clock):
    return HidSession(fake_device, led, clock)


def run_steps(session, count):
    return [session.step() for _ in range(count)]


def test_a_tap_yields_down_then_up(session, fake_device):
    fake_device.feed(*seq.tap())
    edges = [e for e in run_steps(session, len(seq.tap())) if e is not None]
    assert edges == [Edge.DOWN, Edge.UP]


def test_idle_read_timeouts_are_not_edges(session):
    assert run_steps(session, 3) == [None, None, None]


def test_pending_led_colour_is_written_before_the_next_read(session, fake_device, led):
    led.request(Color.GREEN)
    session.step()
    assert fake_device.writes == [led_report(Color.GREEN)]


def test_led_is_written_only_once_per_request(session, fake_device, led):
    led.request(Color.RED)
    run_steps(session, 3)
    assert fake_device.writes == [led_report(Color.RED)]


def test_flush_writes_a_pending_colour_without_reading(session, fake_device, led):
    fake_device.feed(seq.report(seq.TOUCH_BEGIN))
    led.request(Color.RED)
    session.flush_led()
    assert fake_device.writes == [led_report(Color.RED)]
    assert session.step() is Edge.DOWN  # the queued report was not consumed by the flush


def test_silence_past_the_watchdog_raises(session, clock):
    clock.advance(WATCHDOG_S + 0.1)
    with pytest.raises(DeviceError, match="watchdog"):
        session.step()


def test_silence_of_exactly_the_watchdog_is_tolerated(session, clock):
    clock.advance(WATCHDOG_S)
    assert session.step() is None


def test_a_report_after_long_silence_is_not_a_failure(session, fake_device, clock):
    clock.advance(WATCHDOG_S * 10)
    fake_device.feed(seq.report(seq.TOUCH_BEGIN))
    assert session.step() is Edge.DOWN


def test_any_report_including_the_heartbeat_resets_the_watchdog(session, fake_device, clock):
    clock.advance(WATCHDOG_S - 0.1)
    fake_device.feed(seq.report(seq.IDLE))
    session.step()
    clock.advance(WATCHDOG_S - 0.1)
    assert session.step() is None


def test_a_vanished_device_raises_on_read(session, fake_device):
    fake_device.disconnect()
    with pytest.raises(DeviceError):
        session.step()


def test_a_failed_led_write_raises_even_though_reads_still_work(led, clock):
    class WriteFails(FakeHidDevice):
        def write(self, data):
            raise DeviceError("write failed")

    session = HidSession(opened(WriteFails()), led, clock)
    led.request(Color.RED)
    with pytest.raises(DeviceError, match="write failed"):
        session.step()
