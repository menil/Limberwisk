# Releasing

A release is a tag. Pushing `v1.0.0` runs `.github/workflows/release.yml`, which lints and
tests, builds a universal2 app, wraps it in a DMG and creates a **draft** GitHub release.
Review the draft, then publish it.

## Cutting a release

1. Work through [`manual-tests.md`](manual-tests.md); the real-button latency, hotplug and
   Wispr-compatibility gates (specs/spec.md section 8) block a release and are not checked
   by CI. Nothing mechanical stops a tag being pushed before then.
2. Set `__version__` in `src/muteme_flow/__init__.py` to the release version.
3. In `CHANGELOG.md`, rename `[Unreleased]` to the version and date, and start a new
   `[Unreleased]` above it. The workflow's generated notes list the commits; the changelog is
   the human summary, so keep both.
4. Merge, then push the tag (`git tag v1.0.0 && git push origin v1.0.0`).
5. Review the draft release the workflow creates, then publish it.

Details:

- The tag must match the version in `src/muteme_flow/__init__.py` (`v1.0.0` needs
  `__version__ = "1.0.0"`), or the workflow stops before building. A suffix such as
  `v1.0.0-rc1` is accepted and marks the release as a prerelease.
- The workflow only ever creates a draft. If you re-run it for the same tag, delete the old
  draft first, because GitHub allows several drafts for one tag.

## Building locally

```bash
python3 -m venv .venv                     # must be the python.org universal2 Python
.venv/bin/pip install -e '.[dev,build]'
scripts/build_app.sh                      # dist/MuteMe Flow.app, ad-hoc signed
scripts/make_dmg.sh                       # dist/MuteMe-Flow-<version>.dmg
```

`build_app.sh` fails if any native binary in the bundle is single-architecture. So far the
cause has always been a PyPI wheel that is arm64 only (hidapi is); the script builds that
one from source for both architectures.

## Signed and notarized releases

Without a Developer ID certificate the DMG is only ad-hoc signed: it works, but macOS asks
the user to right-click the app and choose Open the first time. To ship a normal install
experience, add these as secrets of a GitHub **environment** named `release`
(Settings > Environments), and give that environment required reviewers and a
deployment-tag rule so that pushing a tag alone cannot reach them:

| Secret | What |
| :--- | :--- |
| `MACOS_CERTIFICATE` | The "Developer ID Application" certificate exported as `.p12`, base64 encoded |
| `MACOS_CERTIFICATE_PASSWORD` | The password set on that export |
| `MACOS_SIGN_IDENTITY` | The identity name, e.g. `Developer ID Application: Name (TEAMID)` |
| `APPLE_ID` | The Apple ID of the developer account |
| `APPLE_TEAM_ID` | The developer team ID |
| `APPLE_APP_PASSWORD` | An app-specific password for that Apple ID |

With them present the workflow signs every native file inside out with the hardened runtime
(`packaging/entitlements.plist`), notarizes the app and the DMG, staples the tickets, and
checks what Gatekeeper says. The same steps work locally with `SIGN_IDENTITY`,
`NOTARY_PROFILE` and (optionally) `NOTARY_KEYCHAIN` set. The secrets are given only to the
step that imports the certificate, never to the install or test steps.

**What has and has not been exercised:** the signing script has been run with an ad-hoc
identity, which proved every one of the bundle's native libraries gets signed with the
hardened runtime and that the app still launches and attaches the device under it. It has
never run with a real certificate, Apple's timestamp service or the notary service, so
expect to iterate on those the first time.

## Known gaps

- Python dependencies are pinned by version, not by hash, so a compromised PyPI release
  could run during the build. The secrets are kept out of those steps for that reason.
- The x86_64 half of the bundle has never been executed on an Intel Mac.

## Before the first release

Work through [`manual-tests.md`](manual-tests.md). The packaged app should be checked on a
Mac that has never run the project, and with a signed build, whether the device can be
opened without an extra permission prompt (specs/spec.md section 7.2).
