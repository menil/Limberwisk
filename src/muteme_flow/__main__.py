"""Command-line entry point; replaced by the menu bar app in a later milestone."""

from muteme_flow import __version__


def main() -> None:
    print(f"MuteMe Flow {__version__}")


if __name__ == "__main__":
    main()
