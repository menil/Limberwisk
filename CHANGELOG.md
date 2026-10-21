# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/).

## [0.3.0](https://github.com/menil/wisprflow-muteme-bridge/compare/v0.2.0...v0.3.0) (2026-10-21)


### Features

* add backend and audio feedback options to settings and menu ([9896434](https://github.com/menil/wisprflow-muteme-bridge/commit/98964349eb9d91136e0031d4869a1b0f8e94632f))
* decouple Controller to coordinate abstract inputs and backends ([4ef2323](https://github.com/menil/wisprflow-muteme-bridge/commit/4ef23231729d98518673c4c4cada1ed8f3d8c144))
* define core protocols for pluggable inputs and dictation targets ([9e52bc3](https://github.com/menil/wisprflow-muteme-bridge/commit/9e52bc3e37697303593447050ff5be49e4fa66d4))
* extract MuteMe input worker and LED sink into adapter ([f371628](https://github.com/menil/wisprflow-muteme-bridge/commit/f371628b410ee8d68334be4349f0845d0396bb3e))
* extract Wispr Flow dispatcher and presence into adapter ([32e29cb](https://github.com/menil/wisprflow-muteme-bridge/commit/32e29cba38297fd09f2569828c9ac76e060e6337))
* implement EnviousWispr dictation backend adapter ([0b8dc93](https://github.com/menil/wisprflow-muteme-bridge/commit/0b8dc9307f8dac0da144423281f88054189fcbaf))
* implement NullFeedbackSink and AudioFeedbackSink ([e1b3990](https://github.com/menil/wisprflow-muteme-bridge/commit/e1b3990af3edfbea5700a9aed209a491a61334cd))

## [0.2.0](https://github.com/menil/wisprflow-muteme-bridge/compare/v0.1.0...v0.2.0) (2026-10-19)


### Features

* build releases from the release PR without a personal token ([6161af2](https://github.com/menil/wisprflow-muteme-bridge/commit/6161af269a0c0a675b7517f0eaffb925763ceeeb))
* open release pull requests that tag and draft each release ([a57a00d](https://github.com/menil/wisprflow-muteme-bridge/commit/a57a00d238bc0232ba1c08ec3dcc242a45754d7c))

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
