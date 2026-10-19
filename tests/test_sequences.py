from support import sequences as seq


def state_codes(reports):
    return [r[3] for r in reports]


def test_tap_matches_recorded_hardware_sequence():
    # Captured on a real device: begin, seven held reports, end, idle.
    assert state_codes(seq.tap()) == [
        seq.TOUCH_BEGIN,
        *[seq.TOUCH_HELD] * 7,
        seq.TOUCH_END,
        seq.IDLE,
    ]


def test_hold_has_one_begin_and_one_end_around_the_held_stream():
    codes = state_codes(seq.hold())
    assert codes[0] == seq.TOUCH_BEGIN
    assert codes[-2:] == [seq.TOUCH_END, seq.IDLE]
    assert codes.count(seq.TOUCH_HELD) == 100


def test_every_report_is_eight_bytes():
    assert all(len(r) == seq.REPORT_SIZE for r in seq.tap() + seq.hold() + seq.idle(3))
