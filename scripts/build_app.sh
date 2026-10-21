#!/bin/bash
# Build "Limberwisk.app" into dist/ as a universal2 (arm64 + x86_64) bundle.
#
#   scripts/build_app.sh                          # ad-hoc signed, for local use and testing
#   SIGN_IDENTITY="Developer ID Application: ..." scripts/build_app.sh
#
# Environment: PYTHON (default .venv/bin/python; must be the python.org universal2 build,
# with the project installed via `pip install -e '.[dev,build]'`), SIGN_IDENTITY, and
# ALLOW_THIN=1 to accept a single-architecture result.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
# Absolute, because one step runs from a different directory.
PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")"
# Apple's toolchain only: a Nix-provided strip/clang earlier on PATH makes py2app hang.
CLEAN_PATH="/usr/bin:/bin:/usr/sbin:/sbin"
clean_env() { env -i HOME="$HOME" PATH="$CLEAN_PATH" "$@"; }

# Must match the exact pin in pyproject.toml (tests/test_packaging.py checks this).
HIDAPI_VERSION="0.15.0"
APP="dist/Limberwisk.app"

is_universal() {
  case "$1" in
    *arm64*x86_64* | *x86_64*arm64*) return 0 ;;
    *) return 1 ;;
  esac
}

require_universal_python() {
  echo "==> Checking the Python is universal2"
  local real archs
  real="$("$PYTHON" -c 'import os, sys; print(os.path.realpath(sys.executable))')"
  archs="$(/usr/bin/lipo -archs "$real")"
  if ! is_universal "$archs" && [ "${ALLOW_THIN:-0}" != 1 ]; then
    echo "Python is [$archs]; a universal2 build needs arm64 and x86_64." >&2
    echo "Install the python.org universal2 package, or set ALLOW_THIN=1." >&2
    exit 1
  fi
}

# hidapi publishes only an arm64 wheel for macOS, so the x86_64 half has to be built here
# (specs/spec.md section 10.1). --no-cache-dir because pip's wheel cache ignores ARCHFLAGS
# and could hand back a thin wheel.
install_universal_hidapi() {
  echo "==> Building a universal2 hidapi $HIDAPI_VERSION wheel"
  rm -rf build/wheels
  clean_env ARCHFLAGS="-arch arm64 -arch x86_64" "$PYTHON" -m pip wheel \
    "hidapi==$HIDAPI_VERSION" --no-binary hidapi --no-deps --no-cache-dir \
    -w build/wheels -q
  "$PYTHON" -m pip install --force-reinstall --no-deps -q build/wheels/hidapi-*.whl
  # Say what was actually built, so a failed universal2 check later is quick to diagnose.
  local extension
  extension="$("$PYTHON" -c 'import hid; print(hid.__file__)')"
  echo "    hid extension architectures: $(/usr/bin/lipo -archs "$extension")"
}

run_py2app() {
  echo "==> Running py2app"
  # Bytecode written by other Python versions (the Nix test shell uses 3.13) would be copied in.
  find src -name __pycache__ -type d -prune -exec rm -rf {} +
  rm -rf dist build/py2app
  # Run from packaging/: from the repository root setuptools reads pyproject.toml's
  # dependencies as install_requires, which py2app rejects.
  (cd packaging && clean_env "$PYTHON" setup.py py2app \
    --dist-dir ../dist --bdist-base ../build/py2app -q)
}

require_universal_bundle() {
  echo "==> Checking every native binary has both architectures"
  [ -d "$APP" ] || { echo "py2app did not produce $APP" >&2; exit 1; }
  local bad=0 file archs
  while IFS= read -r file; do
    archs="$(/usr/bin/lipo -archs "$file" 2>/dev/null || true)"
    [ -z "$archs" ] && continue  # not a Mach-O file
    if ! is_universal "$archs"; then echo "  thin: $file [$archs]" >&2; bad=1; fi
  done < <(find "$APP" -type f \( -name '*.so' -o -name '*.dylib' -o -perm -u+x \))
  if [ "$bad" = 1 ] && [ "${ALLOW_THIN:-0}" != 1 ]; then
    echo "The bundle contains single-architecture binaries (listed above)." >&2
    exit 1
  fi
}

sign() {
  if [ -n "${SIGN_IDENTITY:-}" ]; then
    scripts/sign_app.sh "$APP"
  else
    echo "==> Ad-hoc signing (no SIGN_IDENTITY set: not distributable beyond this machine)"
    /usr/bin/codesign --force --deep --sign - "$APP"
  fi
}

require_universal_python
install_universal_hidapi
run_py2app
require_universal_bundle
sign
echo "==> Built $APP"
