#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build Linux de HelpVA -> dist/HelpVA-x86_64.AppImage
#
# À lancer SOUS LINUX (Ubuntu/Debian) ou sous WSL, depuis la racine du projet :
#     bash tools/build_linux.sh
#
# Étapes : dépendances système -> environnement Python -> PyInstaller ->
#          emballage en AppImage (un seul fichier qui marche sur la plupart
#          des distributions Linux).
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/4 Dépendances système"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-venv python3-tk python3-dev \
       binutils wget file fontconfig desktop-file-utils
else
  echo "   (apt-get absent : installez à la main python3, python3-venv, python3-tk, binutils, wget)"
fi

echo "==> 2/4 Environnement Python (.venv-linux)"
python3 -m venv .venv-linux
# shellcheck disable=SC1091
source .venv-linux/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt pyinstaller

echo "==> 3/4 PyInstaller"
pyinstaller --noconfirm --clean HelpVA_linux.spec
test -x dist/HelpVA

echo "==> 4/4 AppImage"
APPDIR=build/HelpVA.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp dist/HelpVA "$APPDIR/usr/bin/HelpVA"
python - <<'PY'
from PIL import Image
Image.open("assets/logo.png").convert("RGBA").resize((256, 256)).save("build/HelpVA.AppDir/helpva.png")
PY
cat > "$APPDIR/helpva.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=HelpVA
Comment=Le logiciel des assistants virtuels
Exec=HelpVA
Icon=helpva
Categories=Graphics;Utility;
Terminal=false
DESKTOP
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/HelpVA" "$@"
APPRUN
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/HelpVA"

OUTIL=tools/appimagetool-x86_64.AppImage
if [ ! -x "$OUTIL" ]; then
  wget -q -O "$OUTIL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$OUTIL"
fi
# --appimage-extract-and-run : marche même sans FUSE (cas de WSL et des conteneurs)
ARCH=x86_64 "$OUTIL" --appimage-extract-and-run "$APPDIR" dist/HelpVA-x86_64.AppImage

echo
echo "✅ Terminé : dist/HelpVA-x86_64.AppImage ($(du -h dist/HelpVA-x86_64.AppImage | cut -f1))"
