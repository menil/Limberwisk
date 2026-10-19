# MuteMe Flow

A lightweight macOS menu bar app that turns a **MuteMe** USB button into a
push-to-talk / tap-to-toggle control for **Wispr Flow** dictation, with the button's
LED showing whether you are dictating.

> MuteMe Flow is an independent open-source project and is not affiliated with,
> endorsed by, or sponsored by MuteMe or Wispr Flow.

## Status

Early development: the menu bar app is not built yet. The intended behaviour is defined
in [`specs/spec.md`](specs/spec.md):

- **Tap** the button to start dictation, tap again to stop (hands-free).
- **Hold** the button to dictate while held (push-to-talk).
- The LED is red when idle and green while dictating (best-effort: the app cannot read
  Wispr Flow's real state, see spec section 4.3).

## Supported devices

| Device | USB ID | Status |
| :--- | :--- | :--- |
| MuteMe Original (current generation) | `0x3603:0x0001` | Verified on hardware |
| MuteMe Mini variants | `0x3603:0x0002`–`0x0004` | Untested |
| Legacy MuteMe Original / Mini | `0x20A0:0x42DA` / `0x42DB` | Untested |

The untested devices are enabled on a best-effort basis; reports from owners are welcome.

## Requirements

- macOS 13 or later
- Wispr Flow installed
- The official MuteMe app must be quit; it competes for the device and resets the LED

## Development

The pure-Python logic is covered by unit tests that need no device, no Wispr Flow and
no macOS frameworks, so they also run on Linux CI.

```bash
nix-shell                      # tools: just, ruff, pytest, python
just validate                  # lint + format check + tests
```

To run against real hardware, create a virtual environment on macOS:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,build]'   # build adds py2app for the packaging spike
```

Spikes that need a real device or Wispr Flow live in [`spikes/`](spikes/); each has its
own instructions.

## Repository tooling

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
