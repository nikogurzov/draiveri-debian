# Драйвери (Drivers for Debian)

Малка програма за Debian 12/13, която след нова инсталация проверява кои драйвери и кой фърмуер липсват, намира правилните пакети за **този** компютър и ги инсталира с едно натискане. Ако нещо се обърка, бутонът „Върни както беше“ маха всичко, което програмата е сложила.

*A small GTK 4 tool for Debian: checks for missing drivers and firmware after a fresh install, finds the right packages for the hardware, installs them, and can undo everything it did. The interface is in Bulgarian.*

## Инсталиране

```sh
git clone https://github.com/nikogurzov/draiveri-debian.git
cd draiveri-debian
sudo ./install.sh          # на чиста Debian без sudo:  su -c ./install.sh
```

Инсталаторът слага каквото липсва (python3-gi, gir1.2-gtk-4.0, pciutils, pkexec), копира програмата в `/opt/draiveri` и добавя „Драйвери“ в менюто.

## Как работи

| Бутон | Какво прави |
|---|---|
| **Провери** | Само чете: устройства, заредени драйвери, пакети с фърмуер, грешки за фърмуер в дневника на ядрото, microcode за процесора, извора `non-free-firmware`. |
| **Намери драйвери** | Търси за всяко устройство по идентификатора му (modalias): дали ядрото има драйвер, който не е зареден, и какво препоръчва Debian чрез `isenkram`. Работи за всеки лаптоп и компютър, без списък с модели. |
| **Поправи…** | Показва с отметки какво ще направи, иска паролата (pkexec) и инсталира през apt. Нужното е отметнато, препоръките не са. |
| **↶ Върни както беше** | Маха точно пакетите, сложени от програмата (с зависимостите им), връща старите извори на apt и групите. Нищо друго не пипа. |

Какво може да поправи:

- включва `non-free-firmware` в изворите на Debian (без него няма фърмуер за Wi-Fi, видео и звук);
- липсващ фърмуер (`firmware-iwlwifi`, `firmware-realtek`, `firmware-amd-graphics`, `firmware-sof-signed` и др.);
- `intel-microcode` / `amd64-microcode`;
- драйвер от ядрото, който не е зареден;
- драйвера на NVIDIA (`nvidia-driver`, не е отметнат по подразбиране; при Secure Boot след рестарт се потвърждава ключ);
- достъп до дневника на ядрото (групата `adm`), за да се вижда липсващият фърмуер.

Всяка промяна се записва в `/var/lib/draiveri/istoria.json`, а старите извори в `/var/backups/draiveri/`.

## В терминала

```sh
draiveri --text            # проверка
draiveri --text --search   # проверка и търсене
draiveri --fix             # търси и пита за всяка поправка
draiveri --reset           # връща всичко, направено от програмата
```

## Махане

```sh
draiveri --reset           # ако искаш да махнеш и инсталираното от нея
sudo ./install.sh --remove
```

## Тестове

```sh
python3 -m unittest discover -s tests
```

Лиценз: MIT.
