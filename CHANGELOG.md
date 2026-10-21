# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/).

## [0.2.0](https://github.com/menil/limberwisk/compare/v0.1.0...v0.2.0) (2026-10-19)


### Features

* build releases from the release PR without a personal token ([6161af2](https://github.com/menil/limberwisk/commit/6161af269a0c0a675b7517f0eaffb925763ceeeb))
* open release pull requests that tag and draft each release ([a57a00d](https://github.com/menil/limberwisk/commit/a57a00d238bc0232ba1c08ec3dcc242a45754d7c))

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
