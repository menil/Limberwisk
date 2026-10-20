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


def test_custom_backend_name_in_status():
    source = Source(wispr_running=False)
    assert status_message(source, backend_name="EnviousWispr") == "EnviousWispr not running"
    assert status_text(source, backend_name="EnviousWispr") == "Status: EnviousWispr not running"

    failed = Source(command_failed=True)
    assert status_message(failed, backend_name="EnviousWispr") == "EnviousWispr command failed"
    assert status_message(failed, backend_name="Wispr Flow") == "Wispr command failed"


def test_custom_device_name_in_status():
    disconnected = Source(device_connected=False)
    assert status_message(disconnected, device_name="Foot Pedal") == "Foot Pedal not connected"
    assert status_text(disconnected, device_name="Foot Pedal") == "Status: Foot Pedal not connected"

    conflict = Source(conflict=True)
    assert (
        status_message(conflict, device_name="Foot Pedal") == "Official Foot Pedal app is running"
    )

    ready = Source()
    assert status_message(ready, device_name="Foot Pedal") == "Ready (Foot Pedal connected)"


@dataclass
class SourceWithAttributes:
    backend_name: str = "EnviousWispr"
    device_name: str = "Key Switch"
    command_failed: bool = False
    conflict: bool = False
    open_failed: bool = False
    device_connected: bool = True
    wispr_running: bool = False
    recording: bool = False


def test_source_with_metadata_attributes_used_as_fallback():
    src = SourceWithAttributes()
    assert status_message(src) == "EnviousWispr not running"
    assert status_text(src) == "Status: EnviousWispr not running"

    src_disconnected = SourceWithAttributes(device_connected=False)
    assert status_message(src_disconnected) == "Key Switch not connected"
    assert status_text(src_disconnected) == "Status: Key Switch not connected"

    src_ready = SourceWithAttributes(wispr_running=True)
    assert status_message(src_ready) == "Ready (Key Switch connected)"
