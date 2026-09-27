#!/bin/sh
# Turns the PyInstaller bundle in ./stallion into the Linux packages, written to $1 (default /out).
# Runs inside the packaging stage of packaging/linux/Dockerfile.
set -eu
out=${1:-/out}
VERSION=$(./stallion/stallion --version | awk '{print $2}')
export VERSION
mkdir -p "$out"

# Icons for every menu size, from the app logo
mkdir -p icons/hicolor/scalable/apps
cp favicon.svg icons/hicolor/scalable/apps/stallion.svg
for size in 16 24 32 48 64 128 256 512; do
  mkdir -p "icons/hicolor/${size}x${size}/apps"
  rsvg-convert -w "$size" -h "$size" -o "icons/hicolor/${size}x${size}/apps/stallion.png" favicon.svg
done

# Every library the bundle needs from the system must be a declared dependency (nfpm.yaml)
needed=$(find stallion -type f \( -name '*.so*' -o -perm -u+x \) -exec readelf -d {} + 2>/dev/null \
  | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | sort -u)
bundled=$(find stallion \( -type f -o -type l \) -printf '%f\n' | sort -u)
declared=$(sed -n 's/^ *- \(lib[^(]*\)()(64bit)$/\1/p' nfpm.yaml | sort -u)
undeclared=$(printf '%s\n' "$needed" | grep -vxF "$bundled" \
  | grep -vE '^(libc|libm|libdl|libpthread|librt|libutil|libresolv|ld-linux-x86-64)\.so' \
  | grep -vxF "$declared" || true)
if [ -n "$undeclared" ]; then
  echo "The bundle needs system libraries missing from nfpm.yaml:" "$undeclared" >&2
  exit 1
fi
# ...and a glibc and libstdc++ at least as new as the newest symbol versions it uses
versions=$(find stallion -type f \( -name '*.so*' -o -perm -u+x \) -exec readelf -V {} + 2>/dev/null || true)
glibc=$(printf '%s\n' "$versions" | sed -n 's/.*Name: \(GLIBC_[0-9.]*\).*/\1/p' | sort -uV | tail -n 1)
glibcxx=$(printf '%s\n' "$versions" | sed -n 's/.*Name: \(GLIBCXX_[0-9.]*\).*/\1/p' | sort -uV | tail -n 1)
for need in "libc.so.6($glibc)(64bit)" "libstdc++.so.6($glibcxx)(64bit)"; do
  if ! grep -qF -- "- $need" nfpm.yaml; then
    echo "nfpm.yaml must require $need, with the matching deb versions" >&2
    exit 1
  fi
done

desktop-file-validate stallion.desktop
appstreamcli validate --no-net io.github.lam1623.stallion.metainfo.xml

for packager in deb rpm archlinux; do
  nfpm package --config nfpm.yaml --packager "$packager" --target "$out/"
done

# Portable build for any other distribution: unpack it anywhere and run ./stallion, or ./install.sh
portable="stallion-$VERSION-linux-x86_64"
mkdir -p "$portable"
cp -a stallion/. "$portable/"
cp stallion.desktop install.sh LICENSE "$portable/"
cp favicon.svg "$portable/stallion.svg"
tar -C . -czf "$out/$portable.tar.gz" "$portable"

cd "$out"
sha256sum -- *.deb *.rpm *.pkg.tar.zst *.tar.gz > SHA256SUMS
ls -l
