#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKGROOT="$ROOT/build/package"
VERSION="0.12.1-1"
PKG="linux-epub-reader"

rm -rf "$PKGROOT"
install -d "$PKGROOT/DEBIAN" \
  "$PKGROOT/usr/lib/linux-epub-reader/src" \
  "$PKGROOT/usr/bin" \
  "$PKGROOT/usr/share/applications" \
  "$PKGROOT/usr/share/icons/hicolor/scalable/apps"

install -m 0644 "$ROOT/src/linux_epub_reader.py" "$PKGROOT/usr/lib/linux-epub-reader/src/linux_epub_reader.py"
cat > "$PKGROOT/usr/bin/linux-epub-reader" <<'WRAPPER'
#!/usr/bin/env sh
exec /usr/bin/python3 /usr/lib/linux-epub-reader/src/linux_epub_reader.py "$@"
WRAPPER
chmod 0755 "$PKGROOT/usr/bin/linux-epub-reader"
install -m 0644 "$ROOT/share/applications/linux-epub-reader.desktop" "$PKGROOT/usr/share/applications/linux-epub-reader.desktop"
install -m 0644 "$ROOT/share/icons/hicolor/scalable/apps/linux-epub-reader.svg" "$PKGROOT/usr/share/icons/hicolor/scalable/apps/linux-epub-reader.svg"

cat > "$PKGROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: text
Priority: optional
Architecture: all
Depends: python3, python3-tk
Maintainer: Linux EPUB Reader contributors
Description: Local-first dark-mode EPUB reader
 A text-oriented EPUB reader for Linux with a left-hand table of contents,
 bookmarks, search, reading progress and Linux Mint-green accents.
 .
 Adobe DRM is detected but not natively implemented in this application.
EOF

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$PKGROOT" "$ROOT/dist/${PKG}_${VERSION}_all.deb"
echo "Built: $ROOT/dist/${PKG}_${VERSION}_all.deb"
