"""Text a user can paste into a bug report (specs/spec.md section 6)."""

import platform
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from muteme_flow import __version__
from muteme_flow.devices import DeviceId


@dataclass(frozen=True)
class DiagnosticsInfo:
    app_version: str
    macos_version: str
    wispr_version: str | None
    device: DeviceId | None
    status: str


def describe_device(device: DeviceId | None) -> str:
    if device is None:
        return "none connected"
    verified = "verified" if device.verified else "unverified"
    return f"{device.model} {device.vid:#06x}:{device.pid:#06x} ({verified})"


def format_diagnostics(info: DiagnosticsInfo, log_lines: Sequence[str]) -> str:
    header = [
        f"MuteMe Flow {info.app_version}",
        f"macOS {info.macos_version}",
        f"Wispr Flow {info.wispr_version or 'not found'}",
        f"Device: {describe_device(info.device)}",
        f"Status: {info.status}",
        "",
        "Recent log:",
    ]
    return "\n".join([*header, *log_lines]) + "\n"


def wispr_version(workspace: Any, bundle_loader: Any, bundle_id: str) -> str | None:
    """Wispr Flow's version string, read from the installed app's Info.plist."""
    app_url = workspace.URLForApplicationWithBundleIdentifier_(bundle_id)
    if app_url is None:
        return None
    bundle = bundle_loader(app_url)
    info = bundle.infoDictionary() if bundle is not None else None
    version = info.get("CFBundleShortVersionString") if info else None
    return str(version) if version else None


def collect_info(status: str, device: DeviceId | None) -> DiagnosticsInfo:
    from AppKit import NSWorkspace
    from Foundation import NSBundle

    from muteme_flow.commands import WISPR_BUNDLE_ID

    return DiagnosticsInfo(
        app_version=__version__,
        macos_version=platform.mac_ver()[0],
        wispr_version=wispr_version(
            NSWorkspace.sharedWorkspace(), NSBundle.bundleWithURL_, WISPR_BUNDLE_ID
        ),
        device=device,
        status=status,
    )
