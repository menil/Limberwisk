# Manual tests

Everything the automated tests cannot check: it needs the real device, a person, or a
second Mac. Record results in `specs/spec.md` section 10.1 (the spike log), and tick the
matching Beads tasks. Run from source (`.venv/bin/python -m limberwisk`) unless a step says
"packaged app".

Wispr Flow must be running, the official MuteMe app quit, and a MuteMe plugged in.

## 1. The section 4.2 hard gate (blocks relying on the Wispr semantics)

```bash
.venv/bin/python spikes/nsworkspace_dispatch/run.py --reps 10
```

It starts real dictation. Answer the prompts honestly, and switch to another app once when
it asks (its focus self-test). Pass criteria, all four cases:

- [ ] "Observed OK" is 10/10 for every case
- [ ] "Focus changes" is 0 for every case
- [ ] "Dispatch errors" is 0
- [ ] a 4 s recording transcribes correctly after the quick start/stop cases

Paste the table into spec section 10.1. If anything fails, the state machine (spec
section 4) is revised before anything else is trusted.

## 2. The device layer on real hardware

```bash
.venv/bin/python scripts/hardware_smoke_test.py --leds       # red, green, yellow, blue, off, red
.venv/bin/python scripts/hardware_smoke_test.py --seconds 40  # watch events
```

- [ ] the LED shows each colour in order
- [ ] a tap prints `DOWN` then `UP`; a hold prints one `DOWN`, then one `UP` after release
- [ ] unplugging prints `DISCONNECTED`, replugging prints `CONNECTED` within about 1.5 s
- [ ] the LED colour is restored after replugging

## 3. The app, end to end (`scripts/run_headless.py` or the menu bar app)

- [ ] **Tap** the button: Wispr starts dictating, LED green. **Tap** again: it stops, LED red
- [ ] **Hold** the button: dictates while held, stops on release
- [ ] A very quick tap-tap does not leave Wispr stuck recording
- [ ] Quit Wispr: LED turns blue and touching does nothing (Wispr is not relaunched)
- [ ] Start Wispr again: LED returns to red
- [ ] Start dictation, then unplug the button: Wispr stops
- [ ] Start dictation, then put the Mac to sleep and wake it: Wispr is stopped, LED red
- [ ] Start dictation, then `kill -TERM` the app: Wispr stops, LED ends red
- [ ] Wispr's own keyboard shortcut still works alongside the button
- [ ] Focus never moves to Wispr when the button is used

## 4. The menu bar app

- [ ] The menu bar shows the microphone item, and no Dock icon appears
- [ ] The status line is right for: ready, dictating, device unplugged, Wispr not running
- [ ] Hold Threshold: try each choice (250, 350, 500 ms); the hold/tap boundary moves
      accordingly and the choice survives quitting and relaunching
- [ ] Copy Diagnostics puts sensible text on the clipboard (versions, device, recent log,
      no `/Users/<name>` paths)
- [ ] Documentation & Help opens the README
- [ ] Open the menu, then touch the button: it still works while the menu is open
- [ ] **With the official MuteMe app installed** (not available during development):
      launching it turns the menu bar item to `🎙️⚠️`, the LED yellow, and shows the quit
      row; clicking it names the app and quits it. Then read its bundle identifier
      (`osascript -e 'id of app "MuteMe"'`) and put it in `OFFICIAL_APP_BUNDLE_IDS`
      (`src/limberwisk/conflict.py`)

## 5. The packaged app and installer

Build with `scripts/build_app.sh` and `scripts/make_dmg.sh` (see `releasing.md`).

- [ ] Packaged app: launches, finds the device, taps and holds work (the first
      ad-hoc-signed build was checked on the development Mac, without any permission prompt)
- [ ] Packaged app: **Start at Login** toggles, and the item appears in System Settings >
      General > Login Items; toggling it off removes it
- [ ] Mount the DMG on a **Mac that has never run the project**, drag the app to
      Applications, right-click > Open (unsigned build): it runs without Terminal
- [ ] **Signed build** (needs a Developer ID): it opens by double-click, and a notarized
      DMG passes `spctl --assess --type open --context context:primary-signature -vv`
- [ ] **Signed build**: the device still opens with no extra permission prompt, and keeps
      working after a rebuild (specs/spec.md section 7.2)

## 6. Release gates (specs/spec.md section 8)

Already measured without a person (see spec section 10.1); re-run before a release:

```bash
.venv/bin/python scripts/measure_latency.py --taps 100 --holds 10    # software path, gate p95 <= 50 ms
.venv/bin/python scripts/measure_idle.py "dist/Limberwisk.app"         # idle memory and CPU, informational
```

Need a person:

- [ ] **Real-button latency:** run `scripts/run_headless.py`, tap and hold about 30 times,
      quit with Ctrl-C; it prints the touch-to-dispatch summary. p95 must be 50 ms or less
- [ ] **Hotplug:** `.venv/bin/python scripts/measure_hotplug.py --cycles 20`, unplugging and
      replugging when asked; all 20 must be measured and every one within 3 s
- [ ] **Light feels instant:** with the headless runner or the app, hold the button, then
      release it: the light should return to red without a visible lag (measured about
      45 ms in the worst case with a synthetic device)
- [ ] **Wispr compatibility:** sections 1 and 3 above against the installed Wispr Flow
- [ ] **Heartbeat with the official MuteMe app running** (optional, needs that app): does the
      device's idle heartbeat change (spec section 10, question 5)?
