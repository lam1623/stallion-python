#!/bin/sh
# Adds this portable Stallion to your applications menu and to ~/.local/bin, without root.
# ./install.sh --uninstall takes both out again (the folder itself stays where it is).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
bin="$HOME/.local/bin"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$bin/stallion" "$apps/stallion.desktop"
  echo "Stallion removed from the menu."
  exit 0
fi

command -v ffmpeg >/dev/null 2>&1 || echo "Note: Stallion needs FFmpeg; install it with your package manager."
mkdir -p "$bin" "$apps"
ln -sf "$here/stallion" "$bin/stallion"
sed -e "s|^Exec=.*|Exec=$here/stallion|" -e "s|^Icon=.*|Icon=$here/stallion.svg|" \
  "$here/stallion.desktop" > "$apps/stallion.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
echo "Stallion is in your applications menu, and 'stallion' runs it from a terminal."
