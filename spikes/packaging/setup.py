"""py2app configuration for the packaging spike (not the real app bundle).

Run with the project's virtualenv, which already has py2app installed:
    ../../.venv/bin/python setup.py py2app
"""

from setuptools import setup

setup(
    app=["app.py"],
    options={
        "py2app": {
            "plist": {
                "CFBundleIdentifier": "dev.limberwisk.spike",
                "LSUIElement": True,
            },
            "packages": ["rumps", "hid"],
            # The strip step hangs when a Nix-provided `strip` is first on PATH.
            "strip": False,
        }
    },
)
