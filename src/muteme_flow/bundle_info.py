"""Info.plist contents for the packaged app.

Generated from `app_info` rather than written out by hand: the login item only registers
when the running bundle's identifier equals `APP_BUNDLE_ID`, so the two must never drift.
"""

from typing import Any

from muteme_flow import __version__
from muteme_flow.app_info import APP_BUNDLE_ID, APP_NAME

# SMAppService (Start at Login) needs macOS 13.
MINIMUM_MACOS = "13.0"


def info_plist() -> dict[str, Any]:
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": APP_BUNDLE_ID,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        # A menu bar app: no Dock icon, and no flash of one while it launches.
        "LSUIElement": True,
        "LSMinimumSystemVersion": MINIMUM_MACOS,
        "NSHumanReadableCopyright": "Copyright (c) 2026 Meni Livne",
    }
