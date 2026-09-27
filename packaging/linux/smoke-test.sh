#!/bin/sh
# Smoke test of an installed Stallion, run in a fresh distribution container by
# .github/workflows/packages.yml: the CLI, real conversions with the system FFmpeg, the web server
# and, when Xvfb is installed, the desktop window.
#   PORTABLE=1       checks the per-user install of the portable tarball (install.sh) instead
#   SCREENSHOT=file  saves the window to a PNG (needs ImageMagick)
set -u
work=$(mktemp -d)
fail() {
  echo "FAIL: $*" >&2
  [ -f "$work/app.log" ] && tail -n 40 "$work/app.log" >&2
  exit 1
}
cd "$work" || exit 1

echo "== $(. /etc/os-release && echo "$PRETTY_NAME")"
if [ "${PORTABLE:-0}" = 1 ]; then
  PATH="$HOME/.local/bin:$PATH"
  grep -q '^Exec=/' "${XDG_DATA_HOME:-$HOME/.local/share}/applications/stallion.desktop" \
    || fail "no menu entry from install.sh"
else
  for file in /usr/share/applications/stallion.desktop \
    /usr/share/metainfo/io.github.lam1623.stallion.metainfo.xml \
    /usr/share/icons/hicolor/scalable/apps/stallion.svg \
    /usr/share/icons/hicolor/256x256/apps/stallion.png; do
    [ -f "$file" ] || fail "missing $file"
  done
fi
stallion --version || fail "stallion --version"
# Without a scalable font the window shows no text at all: the packages must bring one along
# (ls rather than find, which minimal images such as openSUSE's leave out)
# shellcheck disable=SC2010
ls -R /usr/share/fonts /usr/local/share/fonts 2>/dev/null | grep -qiE '\.(ttf|otf|ttc)$' \
  || fail "no scalable font installed"

# Two formats this FFmpeg can encode: distributions leave out different encoders
ffmpeg -version | head -n 1
ffmpeg -loglevel error -f lavfi -i testsrc2=size=640x360:rate=25 -f lavfi -i sine=frequency=440 -t 3 \
  -c:v libvpx-vp9 -deadline realtime -c:a libopus clip.webm || fail "could not make a test clip"
formats=$(stallion presets | grep -v "missing:" | grep -oE '^  (mp4-h264|webm-vp9|mp3|opus) ' \
  | tr -d ' ' | head -n 2 | paste -sd, -)
echo "converting to $formats"
stallion convert clip.webm -p "$formats" -o out --speed fast || fail "stallion convert"
set -- out/*
[ $# -eq 2 ] || fail "expected two converted files"

stallion serve --port 8799 --token smoke >serve.log 2>&1 &
server=$!
for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8799/api/health >/dev/null && break
  sleep 1
done
curl -fsS http://127.0.0.1:8799/api/health || { cat serve.log; fail "the web server did not start"; }
echo
curl -fs http://127.0.0.1:8799/ | grep -q '<div id="root"' || fail "the web UI is not served"
kill "$server"

if command -v Xvfb >/dev/null; then
  Xvfb :99 -screen 0 1360x860x24 >xvfb.log 2>&1 &
  for _ in $(seq 1 30); do
    [ -S /tmp/.X11-unix/X99 ] && break
    sleep 1
  done
  DISPLAY=:99 stallion >app.log 2>&1 &
  app=$!
  for _ in $(seq 1 60); do
    pgrep -f QtWebEngineProcess >/dev/null && break
    sleep 1
  done
  # Give the page time to load before looking at the window
  sleep 10
  kill -0 "$app" 2>/dev/null || fail "the desktop app exited"
  pgrep -f QtWebEngineProcess >/dev/null || fail "the desktop window has no web view"
  if [ -n "${SCREENSHOT:-}" ]; then
    DISPLAY=:99 import -window root "$SCREENSHOT" || fail "no screenshot"
  fi
  kill "$app"
  echo "desktop window: ok"
fi
echo "PASS"
