from dataclasses import dataclass

import pytest

from muteme_flow.menu_model import (
    CONFLICT_TITLE,
    MENU_TITLE,
    menu_title,
    status_message,
    status_text,
)


@dataclass
class Source:
    command_failed: bool = False
    conflict: bool = False
    open_failed: bool = False
    device_connected: bool = True
    wispr_running: bool = True
    recording: bool = False


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (Source(), "Status: Ready (MuteMe connected)"),
        (Source(recording=True), "Status: Dictating"),
        (Source(device_connected=False), "Status: MuteMe not connected"),
        (Source(wispr_running=False), "Status: Wispr Flow not running"),
        (Source(open_failed=True), "Status: Cannot open device"),
        (Source(conflict=True), "Status: Official MuteMe app is running"),
        (Source(command_failed=True), "Status: Wispr command failed"),
    ],
)
def test_each_condition_in_the_spec_table_has_its_own_line(source, expected):
    assert status_text(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # an unplugged device explains a Wispr that cannot be reached, not the other way round
        (Source(device_connected=False, wispr_running=False), "Status: MuteMe not connected"),
        # the official app is the likely reason the device will not open
        (Source(conflict=True, open_failed=True), "Status: Official MuteMe app is running"),
        (Source(command_failed=True, conflict=True), "Status: Wispr command failed"),
        (Source(open_failed=True, device_connected=False), "Status: Cannot open device"),
    ],
)
def test_overlapping_conditions_show_the_most_useful_one(source, expected):
    assert status_text(source) == expected


def test_the_menu_bar_title_warns_only_during_a_conflict():
    assert menu_title(Source()) == MENU_TITLE
    assert menu_title(Source(conflict=True)) == CONFLICT_TITLE


def test_the_message_is_the_status_line_without_its_label():
    source = Source(wispr_running=False)
    assert status_text(source) == f"Status: {status_message(source)}"
    assert status_message(source) == "Wispr Flow not running"
