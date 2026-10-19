#!/bin/bash
# Package dist/MuteMe Flow.app into a DMG with an /Applications shortcut for drag-install.
#
#   scripts/make_dmg.sh        # writes dist/MuteMe-Flow-<version>.dmg
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
APP="dist/MuteMe Flow.app"
[ -d "$APP" ] || { echo "Build the app first: scripts/build_app.sh" >&2; exit 1; }

version="$("$PYTHON" -c 'import muteme_flow; print(muteme_flow.__version__)')"
# No spaces in the file name: GitHub rewrites them in release asset names.
dmg="dist/MuteMe-Flow-$version.dmg"

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
/usr/bin/ditto "$APP" "$stage/MuteMe Flow.app"
ln -s /Applications "$stage/Applications"

# hdiutil sometimes fails with "Resource busy" on a loaded CI machine; a retry clears it.
for attempt in 1 2 3; do
  if /usr/bin/hdiutil create -volname "MuteMe Flow" -srcfolder "$stage" -ov -format UDZO "$dmg" >/dev/null; then
    break
  fi
  [ "$attempt" = 3 ] && { echo "hdiutil failed three times" >&2; exit 1; }
  sleep 3
done

if [ -n "${SIGN_IDENTITY:-}" ]; then
  /usr/bin/codesign --force --timestamp --sign "$SIGN_IDENTITY" "$dmg"
  # A signing step that quietly produced a bad signature would otherwise only fail at
  # notarization, much later.
  /usr/bin/codesign --verify --verbose=2 "$dmg"
fi
echo "==> Built $dmg"
