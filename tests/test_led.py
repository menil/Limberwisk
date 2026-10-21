import pytest

from limberwisk.led import Color, LedMailbox, led_report


@pytest.mark.parametrize(
    ("color", "code"),
    [(Color.OFF, 0), (Color.RED, 1), (Color.GREEN, 2), (Color.YELLOW, 3), (Color.BLUE, 4)],
)
def test_report_is_exactly_the_report_id_and_one_colour_byte(color, code):
    assert led_report(color) == bytes([0x00, code])


def test_nothing_pending_initially():
    assert LedMailbox().take_pending() is None


def test_request_is_delivered_once():
    mailbox = LedMailbox()
    mailbox.request(Color.GREEN)
    assert mailbox.take_pending() is Color.GREEN
    assert mailbox.take_pending() is None


def test_requests_coalesce_to_the_latest_colour():
    mailbox = LedMailbox()
    mailbox.request(Color.GREEN)
    mailbox.request(Color.RED)
    assert mailbox.take_pending() is Color.RED


def test_resend_requeues_the_last_requested_colour():
    mailbox = LedMailbox()
    mailbox.request(Color.YELLOW)
    mailbox.take_pending()
    mailbox.mark_for_resend()
    assert mailbox.take_pending() is Color.YELLOW


def test_resend_with_no_colour_ever_requested_stays_empty():
    mailbox = LedMailbox()
    mailbox.mark_for_resend()
    assert mailbox.take_pending() is None
