#!/bin/bash
# Construye Prospectos.app y Prospectos-mac.dmg en una Mac con chip Apple (lo usa GitHub Actions;
# también sirve a mano en una Mac con Python 3.13):
#   bash empaquetado/mac/construir.sh 1.0.0
set -euo pipefail
VERSION="${1:-0.0.0}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"
[ "$(uname -m)" = "arm64" ] || { echo "Esta compilación es para Macs con chip Apple (arm64)."; exit 1; }

export PROSPECTOS_DATOS="${TMPDIR:-/tmp}/prospectos-construir"
python3 manage.py collectstatic --noinput -v0
python3 -m PyInstaller --noconfirm prospectos.spec

APP="dist/Prospectos.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp -R dist/Prospectos "$APP/Contents/Resources/prospectos"
cp empaquetado/mac/lanzar.sh "$APP/Contents/MacOS/Prospectos"
chmod +x "$APP/Contents/MacOS/Prospectos"
cp empaquetado/mac/Prospectos.icns "$APP/Contents/Resources/Prospectos.icns"
sed "s/__VERSION__/$VERSION/g" empaquetado/mac/Info.plist > "$APP/Contents/Info.plist"

# Firma «ad hoc» (sin certificado de Apple): macOS la exige en chips Apple y evita el aviso de «dañada».
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# Imagen de disco con acceso directo a Aplicaciones (arrastrar y soltar).
DMG_DIR="dist/dmg"
rm -rf "$DMG_DIR" dist/Prospectos-mac.dmg
mkdir -p "$DMG_DIR"
cp -R "$APP" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Aplicaciones"
cp empaquetado/mac/LEEME.txt "$DMG_DIR/LEEME.txt"
hdiutil create -volname "Prospectos" -srcfolder "$DMG_DIR" -ov -format UDZO dist/Prospectos-mac.dmg
echo "Listo: dist/Prospectos-mac.dmg"
