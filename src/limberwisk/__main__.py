"""Command-line entry point: starts the menu bar app."""

import argparse

from limberwisk import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="limberwisk",
        description="Menu bar bridge between hardware buttons and dictation apps.",
    )
    parser.add_argument("--version", action="version", version=f"Limberwisk {__version__}")
    parser.parse_args(argv)

    # Imported here so --version works, and the package imports, without AppKit/rumps.
    from limberwisk.app import run

    run()


if __name__ == "__main__":
    main()
