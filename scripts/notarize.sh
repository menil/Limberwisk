#!/bin/bash
# Submit a signed app or DMG to Apple's notary service, wait, staple the ticket, and check
# that Gatekeeper now accepts it.
#
#   NOTARY_PROFILE=muteme-flow scripts/notarize.sh "dist/MuteMe Flow.app"
#
# NOTARY_PROFILE names a keychain profile created once with:
#   xcrun notarytool store-credentials muteme-flow --apple-id ... --team-id ... --password ...
# NOTARY_KEYCHAIN (optional) is the keychain that profile lives in.
set -euo pipefail

TARGET="${1:?usage: notarize.sh <app or dmg>}"
: "${NOTARY_PROFILE:?set NOTARY_PROFILE to a notarytool keychain profile}"

auth=(--keychain-profile "$NOTARY_PROFILE")
if [ -n "${NOTARY_KEYCHAIN:-}" ]; then auth+=(--keychain "$NOTARY_KEYCHAIN"); fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

submit="$TARGET"
if [ -d "$TARGET" ]; then
  # notarytool takes a file, so an .app is zipped first.
  submit="$work/notarize.zip"
  /usr/bin/ditto -c -k --keepParent "$TARGET" "$submit"
fi

echo "==> Submitting $TARGET (this can take several minutes)"
result="$(xcrun notarytool submit "$submit" "${auth[@]}" --wait --output-format json)"
id="$(printf '%s' "$result" | /usr/bin/plutil -extract id raw -o - -)"
status="$(printf '%s' "$result" | /usr/bin/plutil -extract status raw -o - -)"
echo "    submission $id: $status"

if [ "$status" != "Accepted" ]; then
  # Apple's log says exactly which file failed and why; without it a rejection is a mystery.
  xcrun notarytool log "$id" "${auth[@]}" >&2
  exit 1
fi

echo "==> Stapling"
xcrun stapler staple "$TARGET"
xcrun stapler validate "$TARGET"

echo "==> Checking what Gatekeeper will say"
if [ -d "$TARGET" ]; then
  /usr/sbin/spctl --assess --type execute -vv "$TARGET"
else
  /usr/sbin/spctl --assess --type open --context context:primary-signature -vv "$TARGET"
fi
