#!/usr/bin/env python3
"""Помощникът, който поправя и връща. Пуска се като root през pkexec от програмата:
   pkexec /usr/bin/python3 -I popravi.py [--comp КОМПОНЕНТ]... [--pkg ПАКЕТ]... [--mod МОДУЛ]... [--adm]
   pkexec /usr/bin/python3 -I popravi.py --reset
Прави само това: добавя компоненти към изворите на Debian, инсталира пакети, зарежда модули и добавя
потребителя в групата adm (за дневника на ядрото). Всяка промяна се записва в /var/lib/drv-marka/istoria.json,
старите извори се пазят в /var/backups/drv-marka, и --reset връща всичко както е било преди програмата."""
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import izvori

PKG = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,80}$")
MOD = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
ISTORIA = "/var/lib/drv-marka/istoria.json"
BACKUPS = "/var/backups/drv-marka"
OLD_DIRS = {"/var/lib/draiveri": "/var/lib/drv-marka", "/var/backups/draiveri": BACKUPS}   # програмата се казваше „draiveri“


def migrate():
    """Пренася историята и старите извори от времето, когато програмата се казваше „draiveri“ (ако новите ги няма)."""
    for old, new in OLD_DIRS.items():
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                shutil.move(old, new)
            except OSError:
                pass
ENV = dict(os.environ, DEBIAN_FRONTEND="noninteractive", LC_ALL="C.UTF-8")


def args(argv):
    got, flags, i = {"--comp": [], "--pkg": [], "--mod": []}, set(), 0
    while i < len(argv):
        if argv[i] in got and i + 1 < len(argv):
            got[argv[i]].append(argv[i + 1])
            i += 2
        elif argv[i] in ("--adm", "--reset", "--backports"):
            flags.add(argv[i])
            i += 1
        else:
            raise SystemExit(f"Непознат аргумент: {argv[i]}")
    comps, pkgs, mods = got["--comp"], got["--pkg"], got["--mod"]
    bad = [c for c in comps if c not in izvori.ALLOWED] + [p for p in pkgs if not PKG.match(p)] + [m for m in mods if not MOD.match(m)]
    if bad:
        raise SystemExit("Отказвам, неправилни имена: " + ", ".join(bad))
    return comps, pkgs, mods, flags


def say(s):
    print(s, flush=True)


def installed():
    out = subprocess.run(["dpkg-query", "-W", "-f=${Package}\t${db:Status-Abbrev}\n"], capture_output=True, text=True).stdout
    return {l.split("\t")[0] for l in out.splitlines() if "\t" in l and l.split("\t")[1].startswith("ii")}


def load_history(path=None):
    if path is None:
        migrate()
    path = path or ISTORIA
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_history(h, path=None):
    if path is None:
        migrate()
    path = path or ISTORIA
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)
    os.chmod(path + ".tmp", 0o644)        # програмата го чете без парола, за да знае има ли какво да връща
    os.replace(path + ".tmp", path)


def caller():
    """Потребителят, който е пуснал pkexec (не root)."""
    uid = os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID")
    return pwd.getpwuid(int(uid)).pw_name if uid and uid.isdigit() and int(uid) != 0 else ""


def in_group(user, group="adm"):
    return group in subprocess.run(["id", "-nG", user], capture_output=True, text=True).stdout.split()


def codename():
    for line in open("/etc/os-release"):
        if line.startswith("VERSION_CODENAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


BPO_FILE = "/etc/apt/sources.list.d/drv-marka-backports.sources"


def ensure_backports(entry):
    """Ако backports не е в изворите, добавя го в отделен файл (при „Върни“ файлът се трие)."""
    cn = codename()
    for f in izvori.files():
        with open(f, errors="replace") as h:
            if f"{cn}-backports" in h.read():
                return cn
    with open(BPO_FILE, "w") as h:
        h.write(f"Types: deb\nURIs: http://deb.debian.org/debian/\nSuites: {cn}-backports\nComponents: main non-free-firmware\n"
                "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n")
    entry["added_files"] = [BPO_FILE]
    say(f"== Добавих {cn}-backports в изворите ({BPO_FILE})")
    return cn


def dkms_check(images):
    """След ново ядро: има ли за него всички DKMS драйвери (NVIDIA и др.), които има текущото."""
    run = os.uname().release
    def mods(k):
        out = subprocess.run(["dkms", "status", "-k", k], capture_output=True, text=True).stdout if shutil.which("dkms") else ""
        return {l.split(",")[0].split("/")[0].strip() for l in out.splitlines() if l.strip().endswith("installed")}
    need, ok = mods(run), True
    for img in images:
        k = img[len("linux-image-"):]
        miss = need - mods(k)
        if miss:
            ok = False
            say(f"!! НЕ РЕСТАРТИРАЙ: за ядро {k} липсват драйверите: {', '.join(sorted(miss))}. Натисни „Върни“.")
        else:
            say(f"== Ядро {k}: всички драйвери са готови" + (f" ({', '.join(sorted(need))})" if need else "") + ".")
    return ok


def fix(comps, pkgs, mods, adm, backports=False):
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "backup": "", "packages": [], "removed": [], "adm": ""}
    if comps:
        say("== Включвам в изворите: " + " ".join(comps))
        backup = f"{BACKUPS}/{time.strftime('%Y%m%d-%H%M%S')}"
        for f in izvori.files():
            with open(f) as h:
                old = h.read()
            new, changed = izvori.add(old, f.endswith(".sources"), comps)
            if changed:
                os.makedirs(backup, exist_ok=True)
                shutil.copy2(f, os.path.join(backup, os.path.basename(f)))
                with open(backup + "/MAP", "a") as m:
                    m.write(f"{os.path.basename(f)}\t{f}\n")
                with open(f, "w") as h:
                    h.write(new)
                entry["backup"] = backup
                say(f"   {f} (старото е запазено в {backup})")
    if adm:
        user = caller()
        if user and not in_group(user):
            subprocess.run(["usermod", "-aG", "adm", user], check=True)
            entry["adm"] = user
            say(f"== {user} е добавен в групата adm. Важи след излизане и влизане отново.")
    try:
        if pkgs:
            before = installed()
            say("== apt-get update")
            if subprocess.run(["apt-get", "update"], env=ENV).returncode != 0:
                raise SystemExit("apt-get update не успя. Провери интернета.")
            target = ["-t", f"{ensure_backports(entry)}-backports"] if backports else []
            if backports:
                subprocess.run(["apt-get", "update"], env=ENV)
            say("== apt-get install " + " ".join(target + pkgs))
            r = subprocess.run(["apt-get", "install", "-y", *target, *pkgs], env=ENV)
            after = installed()
            entry["packages"] = sorted(after - before)        # с всички зависимости: точно каквото е добавено
            entry["removed"] = sorted(before - after)          # apt маха конфликтни пакети (tlp маха power-profiles-daemon)
            if r.returncode != 0:
                raise SystemExit("Инсталирането не успя (виж по-горе).")
            if entry["packages"]:
                say("   Нови пакети: " + " ".join(entry["packages"]))
            if entry["removed"]:
                say("   apt махна: " + " ".join(entry["removed"]) + " (при „Върни“ се слагат обратно)")
        elif comps:
            subprocess.run(["apt-get", "update"], env=ENV)
    finally:
        if entry["backup"] or entry["packages"] or entry["removed"] or entry["adm"] or entry.get("added_files"):
            save_history(load_history() + [entry])
    images = [p for p in pkgs if re.match(r"linux-image-\d", p)]
    if images and not dkms_check(images):
        return
    for m in mods:
        say(f"== modprobe {m}")
        subprocess.run(["modprobe", m])
    say("== ГОТОВО. Рестартирай компютъра, за да се заредят новите драйвери." if pkgs else "== ГОТОВО.")


def removed_from_apt_log(when, log="/var/log/apt/history.log"):
    """За записи от по-стара версия без „removed“: какво е махнал apt при тази поправка (до 10 мин след нея)."""
    try:
        t0 = time.mktime(time.strptime(when, "%Y-%m-%d %H:%M:%S"))
        with open(log, errors="replace") as h:
            text = h.read()
    except (OSError, ValueError):
        return []
    out = []
    for block in text.split("\n\n"):
        m = re.search(r"Start-Date: (\S+)\s+(\S+)", block)
        if not m or "Commandline: apt-get install -y" not in block:
            continue
        t = time.mktime(time.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S"))
        if 0 <= t - t0 <= 600:
            for line in block.splitlines():
                if line.startswith("Remove: "):
                    out += [x.split(":")[0].strip() for x in re.split(r"\),\s*", line[8:]) if x.strip()]
    return out


def reset():
    h = load_history()
    if not h:
        say("Програмата не е променяла нищо. Няма какво да връщам.")
        return
    now = installed()
    kver = os.uname().release          # работещото ядро не се маха
    pkgs = sorted({p for e in h for p in e.get("packages", []) if p in now and not p.endswith(kver)})
    if any(p.endswith(kver) for e in h for p in e.get("packages", [])):
        say(f"!! Работиш с ядро {kver}, сложено от програмата. Него не махам: стартирай със старото и пусни „Върни“ пак.")
    back = []
    for e in h:
        rem = e["removed"] if "removed" in e else removed_from_apt_log(e.get("time", "")) if e.get("packages") else []
        back += [p for p in rem if p not in back and p not in pkgs]
    if pkgs:
        say("== Махам пакетите, сложени от програмата: " + " ".join(pkgs))
        if subprocess.run(["apt-get", "purge", "-y", *pkgs], env=ENV).returncode != 0:
            raise SystemExit("Махането не успя (виж по-горе). Нищо друго не е пипано.")
    for e in reversed(h):            # най-старото копие се връща последно: то е състоянието преди програмата
        b = e.get("backup")
        if b and os.path.exists(b + "/MAP"):
            with open(b + "/MAP") as mp:
                lines = mp.read().splitlines()
            for line in lines:
                name, dest = line.rstrip("\n").split("\t")
                shutil.copy2(os.path.join(b, name), dest)
                say(f"== Върнат е старият {dest}")
        for f in e.get("added_files", []):
            if os.path.exists(f):
                os.remove(f)
                say(f"== Изтрит {f}")
        if e.get("adm"):
            subprocess.run(["gpasswd", "-d", e["adm"], "adm"])
            say(f"== {e['adm']} е изваден от групата adm")
    subprocess.run(["apt-get", "update"], env=ENV)
    back = [p for p in back if p not in installed()]
    if back:
        say("== Слагам обратно махнатото: " + " ".join(back))
        if subprocess.run(["apt-get", "install", "-y", *back], env=ENV).returncode != 0:
            say("   Не успях да ги сложа обратно. Пусни: sudo apt install " + " ".join(back))
    keep = sorted({p for e in h for p in e.get("packages", []) if p.endswith(kver) and p in now})
    shutil.copy2(ISTORIA, ISTORIA.replace(".json", f"-vrnato-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    if keep:      # работещото ядро остава за следващото „Върни“, от старото ядро
        save_history([{"time": time.strftime("%Y-%m-%d %H:%M:%S"), "backup": "", "packages": keep, "removed": [], "adm": ""}])
        say("== Остава само: " + " ".join(keep) + ". Стартирай със старото ядро и натисни „Върни“ пак.")
        return
    os.remove(ISTORIA)
    say("== ГОТОВО. Всичко е както преди програмата. Рестартирай компютъра.")


def main():
    comps, pkgs, mods, flags = args(sys.argv[1:])
    if os.geteuid() != 0:
        raise SystemExit("Трябва да се пусне като root (през pkexec).")
    if "--reset" in flags:
        reset()
    else:
        fix(comps, pkgs, mods, "--adm" in flags, "--backports" in flags)


if __name__ == "__main__":
    main()
