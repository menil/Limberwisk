# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.1.0] - 2026-10-19

First release, unsigned and not notarized. See `docs/manual-tests.md` for what still needs
checking on real hardware before 1.0.0.

### Changed

- The HID read loop wakes less often when idle (250 ms, 40 ms for a second after a touch),
  cutting idle CPU from 0.27% to about 0.12% of a core without delaying the light.
- The idle memory goal is now a 50 MB footprint (measured 45-48 MB).

### Added

- Menu bar app that maps a MuteMe button to Wispr Flow: tap to toggle, hold to talk.
- Light feedback: red idle, green dictating, blue when Wispr Flow is not running, yellow for
  problems.
- Detection of the official MuteMe app, with a confirmation that names what it will quit.
- Hold-threshold setting, Start at Login (installed app), Copy Diagnostics.
- Orderly quit (menu, signals, system terminate): Wispr is stopped and the light left red.
- Universal2 app and DMG build, signing and notarization scripts, and a draft-release workflow.
