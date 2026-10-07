#!/bin/bash
# Transkript.app'i derler, imzalar, .dmg'ye koyar ve notarize eder.
# Yerelde ve CI'da aynı betik çalışır. Ayrıntılar: docs/release.md
#
# Ortam değişkenleri:
#   PYTHON           Python yorumlayıcısı (varsayılan: .venv/bin/python)
#   SIGN_IDENTITY    imza kimliği (varsayılan: Developer ID Application: BURAK CEYLAN (4F8TVA268Y))
#   NOTARY_PROFILE   yerelde notarytool keychain profili (varsayılan: transkript-notary)
#   NOTARY_KEY_PATH, NOTARY_KEY_ID, NOTARY_ISSUER   CI'da App Store Connect API anahtarı
#   SKIP_NOTARIZE=1  notarization'ı atla (hızlı yerel deneme)
#   SELF_TEST_MODEL  model klasörü verilirse imzalı paketle transkript self-test'i yapılır
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-.venv/bin/python}"
IDENTITY="${SIGN_IDENTITY:-Developer ID Application: BURAK CEYLAN (4F8TVA268Y)}"
ENTITLEMENTS="packaging/entitlements.plist"
VERSION="$("$PY" -c 'from src import __version__; print(__version__)')"
APP="dist/Transkript.app"
DMG="dist/Transkript-$VERSION.dmg"

echo "==> audio_tap derleniyor"
mkdir -p build
swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o build/audio_tap

echo "==> PyInstaller ($VERSION)"
rm -rf "$APP" dist/Transkript
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/transkript.spec

echo "==> İmzalama"
sign() {
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$1"
}
# İçten dışa: önce tüm Mach-O dosyaları, sonra iç .framework paketleri, en son .app
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q "Mach-O"; then sign "$f"; fi
done < <(find "$APP/Contents" -type f -print0)
while IFS= read -r -d '' fw; do sign "$fw"; done < <(find "$APP/Contents" -type d -name "*.framework" -print0 | sort -rz)
sign "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

if [[ -n "${SELF_TEST_MODEL:-}" ]]; then
  echo "==> Self-test (imzalı paket, hardened runtime)"
  say -o build/selftest.aiff "Hello, this is a packaging test."
  "$APP/Contents/MacOS/Transkript" --self-test "$SELF_TEST_MODEL" build/selftest.aiff > build/selftest.txt
  cat build/selftest.txt
  grep -qi "test" build/selftest.txt
  # Paket kendi ikilisini alt süreç olarak (ör. multiprocessing resource_tracker) yetim bırakmamalı
  sleep 2
  if pgrep -f "$APP/Contents/MacOS/Transkript" > /dev/null; then
    pgrep -fl "$APP/Contents/MacOS/Transkript" >&2
    pkill -9 -f "$APP/Contents/MacOS/Transkript"  # resource_tracker SIGTERM'i yok sayar
    echo "Self-test sonrası yetim Transkript süreci kaldı" >&2
    exit 1
  fi
fi

echo "==> DMG"
STAGE="build/dmg"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/Transkript.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Transkript" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"

if [[ "${SKIP_NOTARIZE:-0}" != "1" ]]; then
  echo "==> Notarization"
  if [[ -n "${NOTARY_KEY_PATH:-}" ]]; then
    AUTH=(--key "$NOTARY_KEY_PATH" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER")
  else
    AUTH=(--keychain-profile "${NOTARY_PROFILE:-transkript-notary}")
  fi
  xcrun notarytool submit "$DMG" "${AUTH[@]}" --wait --output-format json | tee build/notary.json
  STATUS="$("$PY" -c 'import json; print(json.load(open("build/notary.json"))["status"])')"
  if [[ "$STATUS" != "Accepted" ]]; then
    ID="$("$PY" -c 'import json; print(json.load(open("build/notary.json"))["id"])')"
    xcrun notarytool log "$ID" "${AUTH[@]}"
    echo "Notarization başarısız: $STATUS" >&2
    exit 1
  fi
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  spctl -a -vv -t open --context context:primary-signature "$DMG"
fi

echo "==> Hazır: $DMG"
