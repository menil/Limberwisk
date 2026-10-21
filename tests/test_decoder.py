import pytest
from support import sequences as seq

from limberwisk.decoder import Edge, EdgeDecoder


def edges(reports):
    decoder = EdgeDecoder()
    return [e for e in (decoder.feed(r) for r in reports) if e is not None]


def codes(*values):
    return [seq.report(v) for v in values]


def test_tap_produces_one_down_then_one_up():
    assert edges(seq.tap()) == [Edge.DOWN, Edge.UP]


def test_hold_produces_one_down_then_one_up():
    assert edges(seq.hold()) == [Edge.DOWN, Edge.UP]


def test_idle_heartbeat_alone_produces_nothing():
    assert edges(seq.idle(10)) == []


def test_heartbeat_between_touches_does_not_add_edges():
    assert edges([*seq.tap(), *seq.idle(4), *seq.hold(), *seq.idle(2)]) == [
        Edge.DOWN,
        Edge.UP,
        Edge.DOWN,
        Edge.UP,
    ]


def test_missing_touch_end_still_releases_on_the_first_zero():
    reports = codes(seq.TOUCH_BEGIN, seq.TOUCH_HELD, seq.TOUCH_HELD, seq.IDLE, seq.IDLE)
    assert edges(reports) == [Edge.DOWN, Edge.UP]


def test_up_is_reported_once_even_though_end_and_idle_both_follow():
    reports = codes(seq.TOUCH_BEGIN, seq.TOUCH_END, seq.IDLE, seq.IDLE)
    assert edges(reports) == [Edge.DOWN, Edge.UP]


def test_touch_already_in_progress_at_open_is_ignored_until_a_fresh_begin():
    already_down = codes(seq.TOUCH_HELD, seq.TOUCH_HELD, seq.TOUCH_END, seq.IDLE)
    assert edges([*already_down, *seq.tap()]) == [Edge.DOWN, Edge.UP]


def test_stale_touch_ending_with_idle_also_recovers():
    assert edges([*codes(seq.TOUCH_HELD, seq.IDLE), *seq.tap()]) == [Edge.DOWN, Edge.UP]


def test_begin_during_a_stale_touch_is_a_real_touch():
    assert edges(codes(seq.TOUCH_HELD, seq.TOUCH_BEGIN)) == [Edge.DOWN]


def test_duplicate_begin_while_touching_is_ignored():
    reports = codes(seq.TOUCH_BEGIN, seq.TOUCH_BEGIN, seq.TOUCH_END)
    assert edges(reports) == [Edge.DOWN, Edge.UP]


def test_stray_touch_end_while_ready_is_ignored():
    assert edges(codes(seq.TOUCH_END, seq.IDLE)) == []


@pytest.mark.parametrize("report", [[], [0], [0, 0, 0]])
def test_reports_too_short_to_hold_a_state_are_ignored(report):
    assert EdgeDecoder().feed(report) is None


def test_unknown_state_codes_are_ignored_without_breaking_a_touch():
    reports = codes(seq.TOUCH_BEGIN, 0x7F, seq.TOUCH_HELD, seq.TOUCH_END)
    assert edges(reports) == [Edge.DOWN, Edge.UP]
