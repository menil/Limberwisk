# AI Decision Record: MuteMe Flow spec verified against real hardware

## Context & Goal
The initial spec for MuteMe Flow (a macOS menu bar bridge between a MuteMe USB button and Wispr Flow) was written from assumptions. The goal was to review it, then verify its claims on a real MuteMe Original (0x3603:0x0001) and Wispr Flow 1.6.1174 before any code is written, so implementation tasks start from facts.

## Architecture & Key Decisions
- **Button protocol corrected from captured HID reports.** `data[3]` is `4` (touch begins), `1` (held, ~70 Hz), `2` (touch ends), `0` (idle, also a ~0.5 s heartbeat). The state machine is therefore edge-driven; `0` alone is never a release, and the heartbeat doubles as a device watchdog.
- **Device IDs are an explicit (VID, PID) table** with only 0x3603:0x0001 marked verified; Mini and legacy IDs stay flagged as unverified.
- **Wispr commands are driven through `NSWorkspace.openURLs` (activates=False)** instead of an `open` subprocess, for latency and focus reasons. Observed behaviour (start while recording is a no-op, a stop 100 ms after start is honoured) came from `open -g` only, so the spec labels it "observed" and lists the `NSWorkspace` path as untested.
- **Latch guard downgraded to an optional safety margin** (default 0) because the 100 ms start/stop test showed no stuck recording.
- **Touches are swallowed while Wispr is not running**, since dispatching a `wispr-flow://` URL would launch the app as a side effect.
- **Threading:** HID thread owns reads and LED writes; the main thread owns AppKit, URL dispatch and the state machine.
- Added lifecycle edge cases, debounce, settings/diagnostics/logging, a fake-HID test strategy, and an Open Questions section instead of claiming certainty.

## Alternatives Considered & Rejected
- **Keep the original level-based model (`0x04` down, `0x00` up):** rejected; hardware showed `0x00` is also the idle heartbeat and releases are `0x02` then `0x00`.
- **Keep the 350 ms latch guard as mandatory:** rejected; not needed for correctness in testing, and it adds timer complexity.
- **Keep `open -g` as the dispatch mechanism:** rejected; a subprocess cannot reasonably meet the <25 ms goal.
- **Poll Wispr for real state to keep the LED exact:** deferred out of v1; the LED is best-effort and idempotent commands resync on the next touch.
- **Launch Wispr on touch if it is not running:** rejected as a surprising side effect of pressing a mute button.
- **Treat the Wispr findings as verified:** rejected; they were single manual trials, partly inferred from logs, so they are labelled as observed with the gaps listed.
