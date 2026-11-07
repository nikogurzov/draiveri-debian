"""Събира какво има в компютъра. Само чете: нищо не инсталира и нищо не променя."""
import glob
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import izvori

ENV = dict(os.environ, LC_ALL="C", PATH=os.environ.get("PATH", "") + ":/usr/sbin:/sbin")

OK, INFO, WARN = "ok", "info", "warn"

# Устройства, които наистина трябва да имат драйвер, за да работи компютърът.
VAZHNI = re.compile(r"network|ethernet|wireless|wi-?fi|vga|3d|display|audio|multimedia|bluetooth|non-volatile|sata|usb controller", re.I)


@dataclass
class Device:
    bus: str
    kind: str
    name: str
    driver: str = ""
    module: str = ""
    state: str = INFO
    note: str = ""
    alias: str = ""          # modalias от /sys: по него се търси драйвер в ядрото


@dataclass
class Module:
    name: str
    size_kb: int
    used: int
    description: str = ""


@dataclass
class Package:
    name: str
    version: str
    summary: str = ""


@dataclass
class Finding:
    level: str
    title: str
    detail: str
    package: str = ""
    module: str = ""


@dataclass
class Report:
    system: str = ""
    kernel: str = ""
    devices: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    packages: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    limits: list = field(default_factory=list)
    fixes: list = field(default_factory=list)
    components: set = field(default_factory=set)
    deep: bool = False
    history: list = field(default_factory=list)


@dataclass
class Fix:
    """Едно нещо, което бутонът „Поправи“ може да направи."""
    title: str
    detail: str
    packages: list = field(default_factory=list)
    components: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    default: bool = True
    adm: bool = False
    removes: list = field(default_factory=list)


def run(cmd, timeout=20):
    """Текстът от команда или None, ако я няма или не успее."""
    if not shutil.which(cmd[0], path=ENV["PATH"]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, env=ENV)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def clean_nn(s):
    """„Realtek [10ec]“ → „Realtek“."""
    return re.sub(r"\s*\[[0-9a-fA-F]{4}\]\s*$", "", s).strip()


def judge(kind, driver, module):
    """Какво да кажем за устройство според драйвера му."""
    if driver:
        return OK, ""
    if VAZHNI.search(kind):
        if module:
            return WARN, f"Има драйвер „{module}“, но не е зареден."
        return WARN, "Няма драйвер. Устройството може да не работи."
    return INFO, "Без драйвер. За този вид устройство това обикновено е нормално."


def parse_lspci(text):
    out = []
    for block in text.strip().split("\n\n"):
        f = {}
        for line in block.splitlines():
            k, _, v = line.partition(":")
            if v:
                f.setdefault(k.strip(), v.strip())
        if "Slot" not in f:
            continue
        kind = clean_nn(f.get("Class", ""))
        name = (clean_nn(f.get("Vendor", "")) + " " + clean_nn(f.get("Device", ""))).strip()
        drv, mod = f.get("Driver", ""), f.get("Module", "")
        st, note = judge(kind, drv, mod)
        slot = f["Slot"] if f["Slot"].count(":") == 2 else "0000:" + f["Slot"]
        out.append(Device("PCI", kind, name, drv, mod, st, note, read_file(f"/sys/bus/pci/devices/{slot}/modalias")))
    return out


USB_CLASS = {"01": "Звук", "02": "Комуникация", "03": "Въвеждане", "06": "Снимки", "07": "Принтер", "08": "Памет",
             "09": "USB разклонител", "0a": "Данни", "0b": "Карта", "0e": "Камера", "e0": "Безжично устройство"}


def read_file(p):
    try:
        with open(p, errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def usb_devices(root="/sys/bus/usb/devices"):
    out = []
    for d in sorted(glob.glob(root + "/*")):
        base = os.path.basename(d)
        if ":" in base or not os.path.exists(d + "/idVendor"):
            continue
        cls = read_file(d + "/bDeviceClass")
        drivers, classes, aliases = [], [], []
        for itf in sorted(glob.glob(f"{d}/{base}:*")):
            link = itf + "/driver"
            if os.path.islink(link):
                drivers.append(os.path.basename(os.readlink(link)))
            classes.append(read_file(itf + "/bInterfaceClass"))
            aliases.append(read_file(itf + "/modalias"))
        if cls == "09":      # вътрешните разклонители само пречат в списъка
            continue
        kinds = [USB_CLASS.get(c, "") for c in [cls] + classes if c and c != "00"]
        kind = next((k for k in kinds if k), "USB устройство")
        vid, pid = read_file(d + "/idVendor"), read_file(d + "/idProduct")
        name = (read_file(d + "/manufacturer") + " " + read_file(d + "/product")).strip() or f"{vid}:{pid}"
        names = ", ".join(dict.fromkeys(drivers))
        if names:
            out.append(Device("USB", kind, name, names, "", OK, ""))
        else:
            out.append(Device("USB", kind, name, "", "", WARN, "Няма драйвер за това устройство.", next((a for a in aliases if a), "")))
    return out


def parse_modules(text):
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 3 and p[1].isdigit():
            out.append(Module(p[0], int(p[1]) // 1024, int(p[2]) if p[2].isdigit() else 0))
    return sorted(out, key=lambda m: m.name)


def describe_modules(mods):
    def one(m):
        m.description = (run(["modinfo", "-F", "description", m.name], 5) or "").strip().splitlines()[0:1]
        m.description = m.description[0] if m.description else ""
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, mods))


PACK_RE = re.compile(r"^(firmware-.*|.*-firmware|intel-microcode|amd64-microcode|nvidia-.*|.*-dkms|dkms|bluez-firmware|atmel-firmware|zd1211-firmware)$")


def all_installed(text):
    return {l.split("\t")[0].split(":")[0] for l in text.splitlines() if l.count("\t") >= 3 and l.split("\t")[3].startswith("ii")}


def parse_packages(text):
    out = []
    for line in text.splitlines():
        p = line.split("\t")
        if len(p) >= 4 and p[3].startswith("ii") and PACK_RE.match(p[0].split(":")[0]):
            out.append(Package(p[0].split(":")[0], p[1], p[2]))
    uniq = {x.name: x for x in out}
    return sorted(uniq.values(), key=lambda x: x.name)


FW_RE = [re.compile(r"Direct firmware load for (\S+) failed"),
         re.compile(r"[Ff]ailed to load firmware[ :\"]+([\w./+-]+)"),
         re.compile(r"firmware: failed to load (\S+)")]

FW_PACKAGE = [("iwlwifi", "firmware-iwlwifi"), ("iwl", "firmware-iwlwifi"), ("rtl", "firmware-realtek"), ("rtw", "firmware-realtek"),
              ("ath", "firmware-atheros"), ("qca", "firmware-atheros"), ("brcm", "firmware-brcm80211"), ("cypress", "firmware-brcm80211"),
              ("amdgpu", "firmware-amd-graphics"), ("radeon", "firmware-amd-graphics"), ("i915", "firmware-intel-graphics"), ("xe/", "firmware-intel-graphics"),
              ("nvidia", "firmware-nvidia-graphics"), ("mediatek", "firmware-mediatek"), ("mt7", "firmware-mediatek"), ("intel/sof", "firmware-sof-signed"),
              ("sof", "firmware-sof-signed"), ("intel/ibt", "firmware-iwlwifi"), ("bnx2", "firmware-bnx2"), ("regulatory.db", "wireless-regdb")]


def firmware_package(path):
    p = path.lower()
    for prefix, pkg in FW_PACKAGE:
        if p.startswith(prefix) or ("/" + prefix) in p:
            return pkg
    return ""


def firmware_present(path, root="/lib/firmware"):
    return any(os.path.exists(os.path.join(root, path) + s) for s in ("", ".zst", ".xz"))


def parse_firmware_log(text):
    """Имената на файловете, които ядрото е търсило и не е намерило."""
    seen = []
    for line in text.splitlines():
        for r in FW_RE:
            m = r.search(line)
            if m:
                name = m.group(1).strip('",.:')
                if name and name not in seen:
                    seen.append(name)
                break
    return seen


def firmware_findings(names, installed, exists=firmware_present):
    out = []
    for name in names:
        if exists(name):
            continue             # системата е търсила друга версия, но файлът вече е там
        pkg = firmware_package(name)
        if pkg and pkg in installed:
            out.append(Finding(INFO, f"Търсен файл: {name}", f"Пакетът {pkg} е инсталиран, но няма точно този файл. Често е търсена по-нова версия и устройството работи с друга."))
        elif pkg:
            out.append(Finding(WARN, f"Липсва фърмуер: {name}", f"Вероятно се решава с пакета {pkg}. Той още не е инсталиран.", pkg))
        else:
            out.append(Finding(INFO, f"Търсен файл: {name}", "Не знам от кой пакет идва. Може да не е нужен."))
    return out


def gpu_findings(devices, smi_version, loaded):
    out = []
    for d in devices:
        if d.bus != "PCI" or not re.search(r"vga|3d|display", d.kind, re.I) or "nvidia" not in d.name.lower():
            continue
        if d.driver == "nvidia":
            v = f", версия {smi_version}" if smi_version else ""
            out.append(Finding(OK, "Видеокарта NVIDIA", f"Работи с драйвера на NVIDIA{v}."))
        elif d.driver == "nouveau":
            out.append(Finding(INFO, "Видеокарта NVIDIA", "Работи със свободния драйвер nouveau. За игри и изчисления обикновено е по-добър драйверът на NVIDIA."))
        else:
            out.append(Finding(WARN, "Видеокарта NVIDIA", "Няма зареден драйвер за картата."))
        break
    return out


def summary_findings(devices, others):
    out = list(others)
    bad = [d for d in devices if d.state == WARN]
    for d in bad:
        out.append(Finding(WARN, d.name, f"{d.kind}: {d.note}"))
    return sorted(out, key=lambda f: {WARN: 0, INFO: 2, OK: 1}[f.level])


def microcode_findings(cpuinfo, installed):
    """Обновленията за процесора (microcode) идват от non-free-firmware и често липсват след инсталация."""
    vendor = "intel-microcode" if "GenuineIntel" in cpuinfo else "amd64-microcode" if "AuthenticAMD" in cpuinfo else ""
    if vendor and vendor not in installed:
        return [Finding(WARN, "Липсват поправките за процесора", f"Пакетът {vendor} поправя грешки и пробиви в процесора.", vendor)]
    return []


def resolve_alias(alias):
    """Кой модул на ядрото е за това устройство (по modalias)."""
    out = run(["modprobe", "-R", alias], 5) if alias else None
    return [m for m in (out or "").split() if m]


def kernel_findings(devices, resolve):
    out = []
    for d in devices:
        if d.state != WARN or d.driver:
            continue
        mods = resolve(d.alias)
        if mods:
            out.append(Finding(WARN, f"Драйвер за {d.name}", f"Ядрото има драйвер „{mods[0]}“, но не е зареден. Ще го заредя.", "", mods[0]))
        elif d.alias:
            out.append(Finding(INFO, f"Без драйвер в ядрото: {d.name}", "Ядрото няма драйвер за това устройство. Виж и препоръките на isenkram."))
    return out


def isenkram_findings(names, installed):
    out = []
    for name in names:
        if name not in installed:
            out.append(Finding(INFO, f"Намерен пакет: {name}", "isenkram го препоръчва за устройство в този компютър.", name))
    return out


NONFREE = re.compile(r"^(firmware-(?!linux-free).*|intel-microcode|amd64-microcode|nvidia-.*)$")


def kernel_flavour(kernel):
    """„7.1.13+deb13-amd64“ -> „amd64“ (за linux-headers-…)."""
    m = re.search(r"\+deb\d+-(.+)$", kernel) or re.search(r"-([a-z][a-z0-9-]*)$", kernel)
    return m.group(1) if m else "amd64"


def plan(r, flavour="amd64", removes=lambda pkgs: []):
    """Какво може да поправи бутонът: пакети от находките, драйвер на NVIDIA, липсващи инструменти.
    removes(пакети) казва какво ще махне apt; такива поправки са без отметка и с предупреждение."""
    fixes = _plan(r, flavour)
    for f in fixes:
        gone = [p for p in removes(f.packages) if p not in f.packages] if f.packages else []
        if gone:
            f.default = False
            f.removes = gone
            f.detail += f". ВНИМАНИЕ: ще махне {', '.join(gone)}"
    return fixes


def _plan(r, flavour):
    fixes = []
    for f in r.findings:
        if f.package and f.level in (WARN, INFO):
            comps = ["non-free-firmware"] if NONFREE.match(f.package) else []
            fixes.append(Fix(f.title, f"Инсталира {f.package}", [f.package], comps, default=f.level == WARN))
            continue
        if f.level != WARN:
            continue
        elif f.module:
            fixes.append(Fix(f.title, f"Зарежда драйвера {f.module}", modules=[f.module]))
        elif f.title.startswith("Изворът non-free-firmware"):
            fixes.append(Fix(f.title, "Включва non-free-firmware в изворите на Debian", components=["non-free-firmware"]))
    if NO_LOG in r.limits:
        fixes.append(Fix("Достъп до дневника на ядрото", "Добавя те в групата adm, за да виждам липсващия фърмуер. Важи след излизане и влизане.", adm=True))
    if any("lspci" in x for x in r.limits):
        fixes.append(Fix("Инструментът lspci", "Инсталира pciutils, за да се виждат вътрешните устройства", ["pciutils"]))
    for f in r.findings:
        if f.title == "Видеокарта NVIDIA" and f.level != OK:
            fixes.append(Fix("Драйверът на NVIDIA", "Инсталира официалния драйвер (nvidia-driver). При Secure Boot ще поиска потвърждение на ключ след рестарт.",
                             [f"linux-headers-{flavour}", "nvidia-kernel-dkms", "nvidia-driver", "firmware-misc-nonfree"],
                             ["contrib", "non-free", "non-free-firmware"], default=False))
    return fixes


def fix_command(fixes, helper):
    """Командата за помощника като root."""
    comps, pkgs, mods = [], [], []
    for f in fixes:
        comps += [c for c in f.components if c not in comps]
        pkgs += [p for p in f.packages if p not in pkgs]
        mods += [m for m in f.modules if m not in mods]
    cmd = ["pkexec", "/usr/bin/python3", "-I", helper]
    for c in comps:
        cmd += ["--comp", c]
    for p in pkgs:
        cmd += ["--pkg", p]
    for m in mods:
        cmd += ["--mod", m]
    if any(f.adm for f in fixes):
        cmd.append("--adm")
    return cmd


NO_LOG = "Нямам достъп до дневника на ядрото, затова не виждам липсващ фърмуер. Поправката „Достъп до дневника“ го оправя."
RELOGIN = "Вече си в групата adm, но това важи след излизане и влизане отново в системата. Дотогава не виждам липсващия фърмуер."
ISTORIA = "/var/lib/draiveri/istoria.json"


def adm_pending():
    """Потребителят е добавен в adm, но текущата сесия още е със старите групи."""
    import grp
    import getpass
    try:
        g = grp.getgrnam("adm")
    except KeyError:
        return False
    return getpass.getuser() in g.gr_mem and g.gr_gid not in os.getgroups()


def would_remove(pkgs):
    """Какво ще махне apt, ако инсталираме тези пакети (симулация, без root)."""
    out = run(["apt-get", "-s", "install", *pkgs], 30) or ""
    return [m.group(1) for m in re.finditer(r"^Remv (\S+)", out, re.M)]


def history(path=ISTORIA):
    """Какво е направила програмата досега (за „Върни както беше“)."""
    import json
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def reset_command(helper):
    return ["pkexec", "/usr/bin/python3", "-I", helper, "--reset"]


def collect(progress=lambda s: None, deep=False):
    r = Report()
    osr = read_file("/etc/os-release")
    m = re.search(r'PRETTY_NAME="?([^"\n]+)', osr)
    r.system = m.group(1) if m else "Linux"
    r.kernel = (run(["uname", "-r"]) or "").strip()

    progress("Чета устройствата…")
    pci = run(["lspci", "-vmm", "-k", "-nn"])
    if pci is None:
        r.limits.append("Няма lspci, затова вътрешните устройства не се виждат. Идва с пакета pciutils.")
    else:
        r.devices += parse_lspci(pci)
    r.devices += usb_devices()

    progress("Чета драйверите…")
    r.modules = parse_modules(read_file("/proc/modules"))
    describe_modules(r.modules)

    progress("Чета пакетите…")
    pk = run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${binary:Summary}\t${db:Status-Abbrev}\n"])
    if pk is None:
        r.limits.append("Няма dpkg, затова инсталираните пакети не се виждат.")
    else:
        r.packages = parse_packages(pk)
    installed = all_installed(pk or "")

    progress("Търся липсващ фърмуер…")
    found = []
    log = run(["journalctl", "-k", "-b", "--no-pager", "-q"], 30)
    if not (log or "").strip():
        log = run(["dmesg"])
    if not (log or "").strip():         # без групата adm journalctl връща празно, без грешка
        r.limits.append(RELOGIN if adm_pending() else NO_LOG)
    else:
        found += firmware_findings(parse_firmware_log(log), installed)

    smi = run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 10)
    found += gpu_findings(r.devices, (smi or "").strip().splitlines()[0] if smi and smi.strip() else "", {m.name for m in r.modules})
    found += microcode_findings(read_file("/proc/cpuinfo"), installed)

    r.components = izvori.enabled()
    if r.components and "non-free-firmware" not in r.components:
        found.append(Finding(WARN, "Изворът non-free-firmware не е включен",
                             "Без него Debian не може да инсталира фърмуер за Wi-Fi, видео и звук."))

    if deep:
        progress("Търся драйвери за устройствата…")
        r.deep = True
        found += kernel_findings(r.devices, resolve_alias)
        isen = run(["isenkram-lookup"], 90)
        if isen is None:
            found.append(Finding(WARN, "Липсва търсачката isenkram",
                                 "С нея Debian казва кой пакет е за кое устройство. Инсталирай я и търси отново.", "isenkram-cli"))
        else:
            found += isenkram_findings(isen.split(), installed)

    r.findings = summary_findings(r.devices, found)
    r.fixes = plan(r, kernel_flavour(r.kernel), would_remove)
    r.history = history()
    return r


def verdict(r):
    w = [f for f in r.findings if f.level == WARN]
    if w:
        return WARN, f"Намерени неща за проверка: {len(w)}"
    if r.limits and not r.devices:
        return INFO, "Проверката не успя да прочете устройствата."
    if r.limits:
        return INFO, "Не намерих липсващи драйвери, но част не беше проверена."
    return OK, "Не намерих липсващи драйвери."


def as_text(r):
    L = ["ДРАЙВЕРИ", f"{r.system}, ядро {r.kernel}", "", verdict(r)[1], ""]
    mark = {OK: "✓", INFO: "•", WARN: "!"}
    if r.findings:
        L.append("ПРОВЕРКА")
        for f in r.findings:
            L.append(f"{mark[f.level]} {f.title}: {f.detail}")
        L.append("")
    if r.fixes:
        L.append("МОЖЕ ДА СЕ ПОПРАВИ (draiveri.py --fix)")
        L += [f"{'+' if f.default else '?'} {f.title}: {f.detail}" for f in r.fixes] + [""]
    if r.history:
        n = len({p for e in r.history for p in e.get("packages", [])})
        L += [f"НАПРАВЕНО ОТ ПРОГРАМАТА: {len(r.history)} пъти, {n} пакета (връщане: draiveri.py --reset)", ""]
    if r.limits:
        L.append("НЕ БЕШЕ ПРОВЕРЕНО")
        L += [f"• {x}" for x in r.limits] + [""]
    L.append(f"УСТРОЙСТВА ({len(r.devices)})")
    for d in r.devices:
        L.append(f"{mark[d.state]} [{d.bus}] {d.name} ({d.kind}): {d.driver or 'без драйвер'}")
    L += ["", f"ЗАРЕДЕНИ ДРАЙВЕРИ ({len(r.modules)})"]
    L += [f"  {m.name}: {m.description}" if m.description else f"  {m.name}" for m in r.modules]
    L += ["", f"ФЪРМУЕР И ПАКЕТИ ЗА ДРАЙВЕРИ ({len(r.packages)})"]
    L += [f"  {p.name} {p.version}" for p in r.packages]
    return "\n".join(L) + "\n"
