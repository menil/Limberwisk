"""py2app configuration for the real app. Use `scripts/build_app.sh`, not this directly."""

import sys
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from muteme_flow.app_info import APP_NAME  # noqa: E402
from muteme_flow.bundle_info import info_plist  # noqa: E402

setup(
    name=APP_NAME,
    app=[str(ROOT / "packaging" / "launcher.py")],
    options={
        "py2app": {
            "plist": info_plist(),
            # Only real packages belong here. `hid` is a single-file extension module: listed
            # as a package, py2app copies its binary into a hid.py that shadows the real
            # module and fails with "source code string cannot contain null bytes".
            "packages": ["muteme_flow", "rumps"],
            # Imported lazily inside functions, which the dependency scan can miss.
            "includes": [
                "hid",
                "AppKit",
                "Foundation",
                "ServiceManagement",
            ],
            # Build and test tooling, and unused standard-library pieces, that a menu bar
            # app never imports. rumps and PyObjC were checked: they need email, http, json,
            # urllib, xml and ctypes, so those stay.
            "excludes": [
                "tkinter",
                "unittest",
                "pydoc",
                "pydoc_data",
                "idlelib",
                "turtle",
                "turtledemo",
                "lib2to3",
                "distutils",
                "pip",
                "setuptools",
                "pkg_resources",
                "wheel",
                "py2app",
                "macholib",
                "modulegraph",
                "altgraph",
                "pytest",
                "_pytest",
                "pluggy",
                "yaml",
            ],
            # The strip step hangs when a Nix-provided `strip` is first on PATH, and the
            # saving is small. The build script also uses a clean PATH.
            "strip": False,
            "argv_emulation": False,
        }
    },
)
