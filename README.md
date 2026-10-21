# Limberwisk

A lightweight macOS menu bar app that turns a [**MuteMe**](https://muteme.com) USB button into
a push-to-talk / tap-to-toggle control for [**Wispr Flow**](https://wisprflow.ai) dictation,
with the button's light showing whether you are dictating.

![A MuteMe button glowing green next to a laptop showing a dictation window, above four buttons showing what each light colour means: red is idle, green is dictating, blue means Wispr Flow is not running, and yellow means something needs attention.](docs/images/hero.svg)

> Limberwisk is an independent open-source project and is not affiliated with,
> endorsed by, or sponsored by MuteMe or Wispr Flow.

## Using it

- **Tap** the button to start dictating, tap again to stop (hands-free).
- **Hold** the button to dictate while you hold it (push-to-talk).
- The light shows what is going on:

| Light | Meaning |
| :--- | :--- |
| Red | Idle |
| Green | Dictating |
| Blue | Wispr Flow is not running (touching the button does nothing) |
| Yellow | A problem: see the menu bar item, which says which (below) |

The light is best-effort: Limberwisk cannot read Wispr Flow's real state, so if you start or
stop dictation another way the light can lag until the next touch.

The menu bar item (a microphone) shows the status (for example `Status: Ready (MuteMe
connected)` or `Status: Dictating`) and lets you choose how long a touch must last to count
as a hold (250, 350 or 500 ms), turn on Start at Login, copy diagnostics for a bug report,
open the help page, and quit. It has no Dock icon.

## Installing

Download [**Limberwisk.dmg**](https://github.com/menil/limberwisk/releases/latest/download/Limberwisk.dmg),
the latest release (older versions are on the
[Releases page](https://github.com/menil/limberwisk/releases)). You can also
[build it yourself](docs/releasing.md#building-locally); the DMG is written to `dist/`.

1. Open the DMG and drag **Limberwisk** to Applications.
2. A release that is not notarized (see the release notes) is refused by macOS the first
   time. On macOS 15 and later, try to open it, then go to **System Settings > Privacy &
   Security** and choose **Open Anyway**. On macOS 13 and 14, right-click the app and choose
   Open. Either way you are overriding Gatekeeper for an app that Apple has not checked,
   so only do it for a copy you trust.
3. Quit the official MuteMe app if it is running: it competes for the button and resets the
   light. Limberwisk notices and offers to quit it for you.

Requires macOS 13 or later and [Wispr Flow](https://wisprflow.ai).

## Troubleshooting

| You see | Likely cause and fix |
| :--- | :--- |
| `Status: MuteMe not connected` | The button is unplugged or on a charge-only cable |
| `Status: Wispr Flow not running` | Start Wispr Flow. Touches are ignored until then, on purpose, so the button never launches it |
| `Status: Official MuteMe app is running` | Click the warning row to quit it, or quit it yourself |
| `Status: Cannot open device` | Another program holds the button. Quit the official MuteMe app first |
| `Status: Wispr command failed` | Limberwisk could not reach Wispr Flow; check that it is installed and running |
| `Start at Login (installed app only)` is greyed out | It can only be turned on in the installed app, not when run from source |

**Still stuck?** Choose **Copy Diagnostics** from the menu and paste the result into an issue.
It contains versions, the device model and recent log lines (with your home folder removed),
and never audio or dictated text. The full log is in `~/Library/Logs/Limberwisk/`.

## Supported devices

| Device | USB ID | Status |
| :--- | :--- | :--- |
| MuteMe Original (current generation) | `0x3603:0x0001` | Verified on hardware |
| MuteMe Mini variants | `0x3603:0x0002`–`0x0004` | Untested |
| Legacy MuteMe Original / Mini | `0x20A0:0x42DA` / `0x42DB` | Untested |

The untested devices are enabled on a best-effort basis; reports from owners are welcome.

## Development

The behaviour is specified in [`specs/spec.md`](specs/spec.md). The pure-Python logic is
covered by unit tests that need no device, no Wispr Flow and no macOS frameworks, so they
also run on Linux CI.

```bash
nix-shell                      # tools: just, ruff, pytest, python
just validate                  # lint + format check + tests
```

To run against real hardware, set up the virtual environment described in
[`docs/releasing.md`](docs/releasing.md), then:

```bash
.venv/bin/python -m limberwisk                  # the menu bar app
.venv/bin/pytest tests/test_appkit_contract.py   # checks the real macOS APIs (needs PyObjC)
```

- [`docs/manual-tests.md`](docs/manual-tests.md): everything that needs the real device
- [`docs/releasing.md`](docs/releasing.md): building the app and DMG, and cutting a release
- [`scripts/`](scripts/): build, signing, measurement and hardware test scripts
- [`spikes/`](spikes/): throwaway experiments that settled early questions

### Repository tooling

- **Git hooks** (`.githooks/`, enabled by `direnv allow`): `commit-msg` enforces
  [Conventional Commits](https://www.conventionalcommits.org/) titles and `pre-commit` runs
  `just validate`. They only run locally; the `validate` workflow
  (`.github/workflows/validate.yml`) runs the same checks in CI on every push and pull
  request as a backstop.
- **Automated PR review** (`.github/workflows/pr-review.yml`): needs the repository secret
  `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`) and/or `OPENROUTER_API_KEY`, and the
  action repository must be shared with this one under *Settings > Actions > General*.
- **Beads issue tracking:** `.beads/` is gitignored; `.envrc` provisions a local database on
  `cd` into the repo.
- **Template updates:** the project was scaffolded with
  [Copier](https://copier.readthedocs.io/); run `copier update` to pull upstream tooling changes.

## License

[MIT](LICENSE)
