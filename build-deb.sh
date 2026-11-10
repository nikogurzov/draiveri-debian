#!/bin/sh
# Прави dist/drv-marka_<версия>_all.deb (без root: dpkg-deb --root-owner-group).
set -e
cd "$(dirname "$0")"
V=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' jezgro.py)
umask 022
R=$(mktemp -d)
chmod 755 "$R"
trap 'rm -rf "$R"' EXIT
mkdir -p "$R/DEBIAN" "$R/usr/lib/drv-marka" "$R/usr/bin" "$R/usr/share/applications" "$R/usr/share/doc/drv-marka"
install -m 755 drv-marka.py popravi.py "$R/usr/lib/drv-marka/"
install -m 644 jezgro.py izvori.py "$R/usr/lib/drv-marka/"
ln -s ../lib/drv-marka/drv-marka.py "$R/usr/bin/drv-marka"
install -m 644 debian/com.palamarka.drvmarka.desktop "$R/usr/share/applications/"
install -m 644 README.md "$R/usr/share/doc/drv-marka/"
install -m 644 LICENSE "$R/usr/share/doc/drv-marka/copyright"
sed "s/@VERSION@/$V/; s/@SIZE@/$(du -sk "$R/usr" | cut -f1)/" debian/control > "$R/DEBIAN/control"
install -m 755 debian/postinst "$R/DEBIAN/postinst"
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$R" "dist/drv-marka_${V}_all.deb"
echo "dist/drv-marka_${V}_all.deb"
