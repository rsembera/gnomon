#!/bin/bash
# Turn dist/Gnomon.app into something a stranger can download and open:
# Developer ID signature, Apple notarization, and a notarized .dmg.
#
#   ./scripts/build_release.sh    # first: builds dist/Gnomon.app
#   ./scripts/release.sh          # then:  dist/Gnomon-<version>.dmg
#
# The recipe is the one worked out for EdgeCase and MailRepo (see
# edgecase/docs/Mac_Packaging_Guide.md), written down as a script so it is
# the same every time. It needs, on this Mac:
#   - the Developer ID Application certificate in the keychain
#   - a notarytool keychain profile (one profile serves every app signed by
#     the same team; EdgeCase's is used unless GNOMON_NOTARY_PROFILE says
#     otherwise). To create one:
#       xcrun notarytool store-credentials "<name>" --apple-id <id> --team-id <team>
# Notarization goes to Apple and takes a few minutes each time, twice.

set -euo pipefail
cd "$(dirname "$0")/.."

IDENTITY="${GNOMON_SIGN_IDENTITY:-Developer ID Application: RICHARD L SEMBERA (2GKBD5N2AH)}"
PROFILE="${GNOMON_NOTARY_PROFILE:-EdgeCase Notarization}"
APP=dist/Gnomon.app

[ -d "$APP" ] || { echo "No $APP. Run scripts/build_release.sh first." >&2; exit 1; }
VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Contents/Info.plist")
DMG="dist/Gnomon-$VERSION.dmg"

notarize() {
    # Submit, wait, and insist on "Accepted": notarytool exits 0 even when
    # Apple says no.
    local target="$1" result
    result=$(xcrun notarytool submit "$target" --keychain-profile "$PROFILE" --wait 2>&1) || true
    echo "$result" | grep -E "^ *(id|status):" | sed 's/^ */   /' | sort -u
    if ! echo "$result" | grep -q "status: Accepted"; then
        echo "Notarization of $target was NOT accepted. Apple's log:" >&2
        local id
        id=$(echo "$result" | awk '/^ *id:/ {print $2; exit}')
        [ -n "$id" ] && xcrun notarytool log "$id" --keychain-profile "$PROFILE" >&2 || echo "$result" >&2
        exit 1
    fi
}

echo "== sign the app (Developer ID, hardened runtime)"
# Every library individually FIRST, then the bundle: notarization rejects
# the app otherwise (learned on EdgeCase).
find "$APP" -type f \( -name "*.so" -o -name "*.dylib" \) | while read -r file; do
    codesign --force --options runtime --timestamp --sign "$IDENTITY" "$file" 2> /dev/null
done
codesign --force --options runtime --timestamp --sign "$IDENTITY" --deep "$APP" 2> /dev/null
codesign --verify --deep --strict "$APP"

echo "== notarize the app (a few minutes)"
ditto -c -k --keepParent "$APP" dist/Gnomon.zip
notarize dist/Gnomon.zip
rm dist/Gnomon.zip
xcrun stapler staple "$APP" > /dev/null
spctl --assess --type exec "$APP"   # Gatekeeper's own verdict; fails the script if "rejected"

echo "== build the disk image"
rm -f "$DMG"
./venv-release/bin/dmgbuild -s packaging/dmg_settings.py "Gnomon" "$DMG" > /dev/null
codesign --force --timestamp --sign "$IDENTITY" "$DMG"

echo "== notarize the disk image (a few minutes)"
notarize "$DMG"
xcrun stapler staple "$DMG" > /dev/null
spctl --assess --type open --context context:primary-signature "$DMG"

echo "Released: $DMG ($(du -h "$DMG" | cut -f1 | tr -d ' '))"
echo "SHA-256:  $(shasum -a 256 "$DMG" | cut -d' ' -f1)"
