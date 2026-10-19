"""Command-line entry point: starts the menu bar app."""

import argparse

from muteme_flow import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="muteme-flow", description="Menu bar bridge between a MuteMe button and Wispr Flow."
    )
    parser.add_argument("--version", action="version", version=f"MuteMe Flow {__version__}")
    parser.parse_args(argv)

    # Imported here so --version works, and the package imports, without AppKit/rumps.
    from muteme_flow.app import run

    run()


if __name__ == "__main__":
    main()
