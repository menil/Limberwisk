#!/bin/bash
# Sign an app with a Developer ID certificate and the hardened runtime, then verify it.
#
#   SIGN_IDENTITY="Developer ID Application: Name (TEAMID)" scripts/sign_app.sh "dist/MuteMe Flow.app"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$(cd "$(dirname "${1:?usage: sign_app.sh <app>}")" && pwd)/$(basename "$1")"
: "${SIGN_IDENTITY:?set SIGN_IDENTITY to the Developer ID Application identity}"
ENTITLEMENTS="$ROOT/packaging/entitlements.plist"

# --timestamp and --options runtime are both required for notarization.
sign() { /usr/bin/codesign --force --timestamp --options runtime --sign "$SIGN_IDENTITY" "$@"; }
is_macho() { /usr/bin/lipo -archs "$1" >/dev/null 2>&1; }

# Not `codesign --deep`: it only descends into the standard nested-code folders, and py2app
# keeps its extensions under Contents/Resources/lib, so they would stay unsigned and
# notarization would reject the app. Everything is signed explicitly, innermost first.
echo "==> Signing native libraries"
find "$APP" -type f \( -name '*.so' -o -name '*.dylib' \) -print0 |
  while IFS= read -r -d '' file; do sign "$file"; done

echo "==> Signing executables"
find "$APP/Contents" -type f -perm -u+x ! -name '*.so' ! -name '*.dylib' -print0 |
  while IFS= read -r -d '' file; do
    if is_macho "$file"; then sign --entitlements "$ENTITLEMENTS" "$file"; fi
  done

echo "==> Signing frameworks"
find "$APP/Contents/Frameworks" -maxdepth 1 -name '*.framework' -print0 2>/dev/null |
  while IFS= read -r -d '' framework; do sign "$framework"; done

echo "==> Signing the app"
sign --entitlements "$ENTITLEMENTS" "$APP"

echo "==> Verifying"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
