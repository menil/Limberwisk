import pytest
from support.clock import FakeClock

from muteme_flow.latency import LatencyRecorder


@pytest.fixture
def clock():
    return FakeClock(start=0.0)


def test_no_summary_before_any_sample(clock):
    assert LatencyRecorder(clock).summary() is None


def test_records_the_time_from_input_to_dispatch_in_milliseconds(clock):
    recorder = LatencyRecorder(clock)
    recorder.input_received(clock())
    clock.advance(0.012)
    recorder.dispatched()
    assert recorder.samples_ms == [pytest.approx(12.0)]


def test_a_dispatch_with_no_input_in_progress_records_nothing(clock):
    recorder = LatencyRecorder(clock)
    recorder.dispatched()
    assert recorder.samples_ms == []


def test_clear_input_stops_later_dispatches_from_being_attributed_to_it(clock):
    recorder = LatencyRecorder(clock)
    recorder.input_received(clock())
    recorder.clear_input()
    clock.advance(1)
    recorder.dispatched()
    assert recorder.samples_ms == []


def test_the_input_time_can_be_taken_earlier_on_another_thread(clock):
    recorder = LatencyRecorder(clock)
    stamped = recorder.now()
    clock.advance(0.020)
    recorder.input_received(stamped)
    clock.advance(0.005)
    recorder.dispatched()
    assert recorder.samples_ms == [pytest.approx(25.0)]


def test_summary_reports_median_p95_and_max(clock):
    recorder = LatencyRecorder(clock)
    for millis in range(1, 101):
        recorder.input_received(clock())
        clock.advance(millis / 1000)
        recorder.dispatched()
    summary = recorder.summary()
    assert summary.count == 100
    assert summary.p50_ms == pytest.approx(50.5)
    assert summary.p95_ms == pytest.approx(96.0)
    assert summary.max_ms == pytest.approx(100.0)


def test_only_the_most_recent_samples_are_kept(clock):
    recorder = LatencyRecorder(clock, capacity=3)
    for _ in range(5):
        recorder.input_received(clock())
        recorder.dispatched()
    assert len(recorder.samples_ms) == 3
