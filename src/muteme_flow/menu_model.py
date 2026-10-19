"""What the menu says, decided without touching any UI code (specs/spec.md sections 5, 6)."""

from typing import Protocol

MENU_TITLE = "🎙️"
CONFLICT_TITLE = "🎙️⚠️"
MODE_LINE = "Mode: Dual (Tap to Toggle / Hold for PTT)"
CONFLICT_ITEM = "⚠️ Official MuteMe app is running (click to quit)"


class StatusSource(Protocol):
    @property
    def command_failed(self) -> bool: ...

    @property
    def conflict(self) -> bool: ...

    @property
    def open_failed(self) -> bool: ...

    @property
    def device_connected(self) -> bool: ...

    @property
    def wispr_running(self) -> bool: ...

    @property
    def recording(self) -> bool: ...


def status_message(source: StatusSource) -> str:
    """The single most useful status; earlier conditions explain later ones."""
    if source.command_failed:
        return "Wispr command failed"
    if source.conflict:
        # The official app holding the device is also why the device may not open.
        return "Official MuteMe app is running"
    if source.open_failed:
        return "Cannot open device"
    if not source.device_connected:
        return "MuteMe not connected"
    if not source.wispr_running:
        return "Wispr Flow not running"
    if source.recording:
        return "Dictating"
    return "Ready (MuteMe connected)"


def status_text(source: StatusSource) -> str:
    return f"Status: {status_message(source)}"


def menu_title(source: StatusSource) -> str:
    return CONFLICT_TITLE if source.conflict else MENU_TITLE
