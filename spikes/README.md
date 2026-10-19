# Spikes

Throwaway experiments that retire risks from `specs/spec.md` section 10. They are not
part of the shipped app and are not covered by `just validate` tests.

| Spike | Question | How to run |
| :--- | :--- | :--- |
| [`packaging/`](packaging/) (superseded by the real build in `../packaging/` and `../scripts/build_app.sh`; kept as a record) | Do py2app, hidapi and rumps bundle on Python 3.14 (universal2)? | install the `build` extra, then `cd spikes/packaging && ../../.venv/bin/python setup.py py2app` (see the notes in `setup.py`), then open `dist/app.app` |
| [`nsworkspace_dispatch/`](nsworkspace_dispatch/) | Do the section 4.2 command semantics hold through `NSWorkspace.openURLs` with `activates=False`, without stealing focus? | `.venv/bin/python spikes/nsworkspace_dispatch/run.py --reps 10` (starts real dictation; needs a person to answer the prompts and to switch apps once for the focus self-test) |

Record results in `specs/spec.md` (section 10.1), not here.
