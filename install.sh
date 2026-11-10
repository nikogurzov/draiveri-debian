#!/bin/sh
# Инсталира „Драйвери“ в /opt/drv-marka, с икона в менюто и команда drv-marka.
#   sudo ./install.sh            инсталира (или обновява)
#   sudo ./install.sh --remove   маха програмата (поправките се връщат преди това с drv-marka --reset)
# Без sudo на чиста Debian: su -c ./install.sh
set -e
DEST=/opt/drv-marka
APP=/usr/share/applications/com.palamarka.drvmarka.desktop
BIN=/usr/local/bin/drv-marka

if [ "$(id -u)" != 0 ]; then
    echo "Пусни ме като root:  sudo ./install.sh   (или  su -c ./install.sh)"
    exit 1
fi

if [ "$1" = "--remove" ]; then
    if [ -s /var/lib/drv-marka/istoria.json ]; then
        echo "Внимание: програмата е инсталирала неща. Ако искаш и тях да махнеш, първо пусни:  drv-marka --reset"
    fi
    rm -rf "$DEST" "$APP" "$BIN"
    echo "Програмата е махната. Историята остава в /var/lib/drv-marka."
    exit 0
fi

SRC=$(cd "$(dirname "$0")" && pwd)
NEED=""
for p in python3 python3-gi gir1.2-gtk-4.0 pciutils pkexec; do
    dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null | grep -q '^ii' || NEED="$NEED $p"
done
if [ -n "$NEED" ]; then
    echo "Инсталирам нужното за програмата:$NEED"
    apt-get update
    # shellcheck disable=SC2086
    apt-get install -y $NEED
fi

mkdir -p "$DEST"
cp "$SRC"/drv-marka.py "$SRC"/jezgro.py "$SRC"/izvori.py "$SRC"/popravi.py "$DEST"/
chown -R root:root "$DEST"
chmod 755 "$DEST" "$DEST"/drv-marka.py "$DEST"/popravi.py
chmod 644 "$DEST"/jezgro.py "$DEST"/izvori.py
ln -sf "$DEST/drv-marka.py" "$BIN"

cat > "$APP" <<EOF
[Desktop Entry]
Type=Application
Name=Драйвери (drv-marka)
Name[en]=Drivers
Comment=Проверка, търсене и инсталиране на драйвери
Comment[en]=Check, find and install drivers on Debian
Exec=$DEST/drv-marka.py
Icon=preferences-system
Terminal=false
Categories=System;Settings;HardwareSettings;
StartupWMClass=com.palamarka.drvmarka
EOF
chmod 644 "$APP"
echo "Готово. „Драйвери (drv-marka)“ е в менюто, а в терминала: drv-marka --text"
