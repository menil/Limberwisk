# Releasing

Releases are driven by Conventional Commit titles. `.github/workflows/release-please.yml`
keeps one "release" pull request open on `main`; it bumps `__version__` and adds the commits
to `CHANGELOG.md`. Merging that PR creates the `vX.Y.Z` tag and a **draft** GitHub release,
and the same workflow then calls `.github/workflows/release.yml`, which lints and tests,
builds a universal2 app, wraps it in a DMG and adds it to the draft. Review the draft, then
publish it.

## Cutting a release

1. Work through [`manual-tests.md`](manual-tests.md); the real-button latency, hotplug and
   Wispr-compatibility gates (specs/spec.md section 8) block a release and are not checked
   by CI. Nothing mechanical stops the release PR being merged before then.
2. Open the "release" pull request that `release-please` maintains, check the version it
   chose and its changelog entry (edit the PR if they need changing), and merge it. `feat:`
   commits raise the minor version and `fix:` commits the patch version. A `!` after the
   type, or a `BREAKING CHANGE:` footer, raises the minor version while the version is
   below 1.0.0 and the major version after that. To force a version, add a commit with a
   `Release-As: 1.0.0` footer.
3. Wait for the Release workflow to finish, then review the draft release it filled in
   (the files, the install notes and the SHA-256) and publish it.
   The release carries the DMG twice, as `Limberwisk-<version>.dmg` and as `Limberwisk.dmg`:
   the README links to `releases/latest/download/Limberwisk.dmg`, which GitHub resolves to
   the newest published release that is not a draft or prerelease.

Details:

- The tag must match the version in `src/limberwisk/__init__.py`, or the workflow stops
  before building. The release PR keeps them in step (`__version__` carries an
  `x-release-please-version` marker so it can be edited).
- Pushing a tag by hand still works (`git tag v0.2.0 && git push origin v0.2.0`, after
  setting `__version__`): the workflow then creates the draft itself. A suffix such as
  `v0.2.0-rc1` is accepted and marks the release as a prerelease.
- If you re-run the workflow for the same tag it replaces the files, and does not add the
  install notes twice. A hand-pushed tag that already has a draft needs the old draft
  deleted first, because GitHub allows several drafts for one tag.
- `release-please` does not use an `[Unreleased]` heading; it adds each version above the
  previous one. The 0.1.0 entry was written by hand.

### Repository setting

`release-please` works with the built-in `GITHUB_TOKEN`, but GitHub only lets Actions open
pull requests if **Settings > Actions > General > Workflow permissions > Allow GitHub Actions
to create and approve pull requests** is ticked. Tags made with that token start no
workflow, so `release-please.yml` calls `release.yml` itself (with the tag as an input) when
it has made a release. The same token means the release PR gets no CI checks; it only
changes the version and the changelog, and `Validate` runs on `main` after the merge. If
you ever make a check required on pull requests, give `release-please` a personal access
token instead (the action's `token:` input), so its PR runs the checks too.

## Building locally

```bash
python3 -m venv .venv                     # must be the python.org universal2 Python
.venv/bin/pip install -e '.[dev,build]'
scripts/build_app.sh                      # dist/Limberwisk.app, ad-hoc signed
scripts/make_dmg.sh                       # dist/Limberwisk-<version>.dmg
```

`build_app.sh` fails if any native binary in the bundle is single-architecture. So far the
cause has always been a PyPI wheel that is arm64 only (hidapi is); the script builds that
one from source for both architectures.

## Signed and notarized releases

Without a Developer ID certificate the DMG is only ad-hoc signed: it works, but macOS
refuses it the first time, and the user has to override that:

- macOS 15 and later: choose **Open Anyway** in System Settings > Privacy & Security.
- macOS 13 and 14: right-click the app and choose Open.

To ship a normal install experience, add these as secrets of a GitHub **environment** named `release`
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
