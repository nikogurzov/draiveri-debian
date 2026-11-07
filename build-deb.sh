#!/bin/sh
# Прави dist/draiveri_<версия>_all.deb (без root: dpkg-deb --root-owner-group).
set -e
cd "$(dirname "$0")"
V=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' jezgro.py)
umask 022
R=$(mktemp -d)
chmod 755 "$R"
trap 'rm -rf "$R"' EXIT
mkdir -p "$R/DEBIAN" "$R/usr/lib/draiveri" "$R/usr/bin" "$R/usr/share/applications" "$R/usr/share/doc/draiveri"
install -m 755 draiveri.py popravi.py "$R/usr/lib/draiveri/"
install -m 644 jezgro.py izvori.py "$R/usr/lib/draiveri/"
ln -s ../lib/draiveri/draiveri.py "$R/usr/bin/draiveri"
install -m 644 debian/com.palamarka.draiveri.desktop "$R/usr/share/applications/"
install -m 644 README.md "$R/usr/share/doc/draiveri/"
install -m 644 LICENSE "$R/usr/share/doc/draiveri/copyright"
sed "s/@VERSION@/$V/; s/@SIZE@/$(du -sk "$R/usr" | cut -f1)/" debian/control > "$R/DEBIAN/control"
install -m 755 debian/postinst "$R/DEBIAN/postinst"
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$R" "dist/draiveri_${V}_all.deb"
echo "dist/draiveri_${V}_all.deb"
