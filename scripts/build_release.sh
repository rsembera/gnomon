#!/bin/bash
# Build the copy of Gnomon that OTHER PEOPLE can run.
#
#   ./scripts/build_release.sh        ->  dist/Gnomon.app
#
# Why this is not just `python setup_app.py py2app` from the usual venv:
# that venv is Homebrew's Python, and Homebrew compiles Python for the Mac
# it is installed on. An app bundled from it opens only on that version of
# macOS or newer (macOS 27 at the time of writing), whatever its Info.plist
# claims. The Python from python.org is the same Python built to run on
# macOS 10.15 and up, so an app bundled from IT runs wherever Gnomon's own
# code does: Apple Silicon, macOS 12 or newer.
#
# One-time setup: install Python 3.14 from https://www.python.org/downloads/
# (the macOS universal installer). It sits beside Homebrew's and replaces
# nothing. This script makes its own venv (venv-release/) from it.
#
# The result is ad-hoc signed: it runs on this Mac. Giving it to anyone else
# still needs Developer ID signing and notarization (see README).

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
APP=dist/Gnomon.app

if [ ! -x "$PYTHON" ]; then
    echo "Python 3.14 from python.org is not installed (looked for $PYTHON)." >&2
    echo "Install the macOS universal installer from https://www.python.org/downloads/" >&2
    exit 1
fi

echo "== venv-release (python.org $("$PYTHON" --version | cut -d' ' -f2))"
[ -d venv-release ] || "$PYTHON" -m venv venv-release
./venv-release/bin/pip install --quiet --upgrade pip
./venv-release/bin/pip install --quiet -r requirements-dev.txt

echo "== tests, under the Python that will be shipped"
./venv-release/bin/python -m pytest -q | tail -1

echo "== build"
rm -rf build dist
./venv-release/bin/python setup_app.py py2app --arch arm64 > build.log 2>&1 \
    || { tail -20 build.log >&2; exit 1; }
rm -f build.log

# Every compiled file in the bundle, one path per line.
compiled_files() {
    find "$APP" -type f | while read -r file; do
        if file -b "$file" | grep -q "Mach-O"; then echo "$file"; fi
    done
}

echo "== Apple Silicon only: drop the Intel half of each compiled file"
# python.org's Python is universal (Intel + Apple Silicon). Gnomon is Apple
# Silicon only, so the Intel halves are dead weight.
compiled_files | while read -r file; do
    if lipo -archs "$file" | grep -q x86_64; then
        lipo "$file" -thin arm64 -output "$file.thin" && mv "$file.thin" "$file"
    fi
done

echo "== check: nothing in the bundle needs a newer macOS than it declares"
DECLARED=$(/usr/libexec/PlistBuddy -c "Print :LSMinimumSystemVersion" "$APP/Contents/Info.plist")
FAILED=0
while read -r file; do
    [ "$(lipo -archs "$file")" = "arm64" ] || { echo "  not arm64-only: $file" >&2; FAILED=1; }
    NEEDS=$(otool -l "$file" | grep -A4 LC_BUILD_VERSION | awk '/minos/ {print $2}' | sort -V | tail -1)
    if [ -n "$NEEDS" ] && [ "$(printf '%s\n%s\n' "$NEEDS" "$DECLARED" | sort -V | tail -1)" != "$DECLARED" ]; then
        echo "  needs macOS $NEEDS (declared $DECLARED): $file" >&2
        FAILED=1
    fi
done < <(compiled_files)
[ "$FAILED" = 0 ] || { echo "Bundle check FAILED." >&2; exit 1; }
echo "   $(compiled_files | wc -l | tr -d ' ') compiled files, all Apple Silicon, all run on macOS $DECLARED or newer"

echo "== sign (ad-hoc: enough for this Mac, not for anyone else's)"
codesign --force --deep -s - "$APP" 2> /dev/null
codesign --verify --deep --strict "$APP"

VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Contents/Info.plist")
echo "Built $APP: Gnomon $VERSION, $(du -sh "$APP" | cut -f1 | tr -d ' '), Apple Silicon, macOS $DECLARED+"
