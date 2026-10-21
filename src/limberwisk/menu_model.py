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


def status_message(
    source: StatusSource,
    backend_name: str | None = None,
    device_name: str | None = None,
) -> str:
    """The single most useful status; earlier conditions explain later ones."""
    effective_backend = (
        backend_name if backend_name is not None else getattr(source, "backend_name", "Wispr Flow")
    )
    effective_device = (
        device_name if device_name is not None else getattr(source, "device_name", "MuteMe")
    )

    if source.command_failed:
        return (
            "Wispr command failed"
            if effective_backend == "Wispr Flow"
            else f"{effective_backend} command failed"
        )
    if source.conflict:
        # The official app holding the device is also why the device may not open.
        return f"Official {effective_device} app is running"
    if source.open_failed:
        return "Cannot open device"
    if not source.device_connected:
        return f"{effective_device} not connected"
    if not source.wispr_running:
        return f"{effective_backend} not running"
    if source.recording:
        return "Dictating"
    return f"Ready ({effective_device} connected)"


def status_text(
    source: StatusSource,
    backend_name: str | None = None,
    device_name: str | None = None,
) -> str:
    return f"Status: {status_message(source, backend_name=backend_name, device_name=device_name)}"


def menu_title(source: StatusSource) -> str:
    return CONFLICT_TITLE if source.conflict else MENU_TITLE
