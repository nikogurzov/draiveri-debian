#!/bin/sh
# Инсталира „Драйвери“ в /opt/draiveri, с икона в менюто и команда draiveri.
#   sudo ./install.sh            инсталира (или обновява)
#   sudo ./install.sh --remove   маха програмата (поправките се връщат преди това с draiveri --reset)
# Без sudo на чиста Debian: su -c ./install.sh
set -e
DEST=/opt/draiveri
APP=/usr/share/applications/com.palamarka.draiveri.desktop
BIN=/usr/local/bin/draiveri

if [ "$(id -u)" != 0 ]; then
    echo "Пусни ме като root:  sudo ./install.sh   (или  su -c ./install.sh)"
    exit 1
fi

if [ "$1" = "--remove" ]; then
    if [ -s /var/lib/draiveri/istoria.json ]; then
        echo "Внимание: програмата е инсталирала неща. Ако искаш и тях да махнеш, първо пусни:  draiveri --reset"
    fi
    rm -rf "$DEST" "$APP" "$BIN"
    echo "Програмата е махната. Историята остава в /var/lib/draiveri."
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
cp "$SRC"/draiveri.py "$SRC"/jezgro.py "$SRC"/izvori.py "$SRC"/popravi.py "$DEST"/
chown -R root:root "$DEST"
chmod 755 "$DEST" "$DEST"/draiveri.py "$DEST"/popravi.py
chmod 644 "$DEST"/jezgro.py "$DEST"/izvori.py
ln -sf "$DEST/draiveri.py" "$BIN"

cat > "$APP" <<EOF
[Desktop Entry]
Type=Application
Name=Драйвери
Name[en]=Drivers
Comment=Проверка, търсене и инсталиране на драйвери
Comment[en]=Check, find and install drivers on Debian
Exec=$DEST/draiveri.py
Icon=preferences-system
Terminal=false
Categories=System;Settings;HardwareSettings;
StartupWMClass=com.palamarka.draiveri
EOF
chmod 644 "$APP"
echo "Готово. „Драйвери“ е в менюто, а в терминала: draiveri --text"
