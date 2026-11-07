"""Изворите на apt (sources.list и .sources): кои компоненти са включени за Debian и как да се добавят."""
import glob
import re

DEBIAN_URI = re.compile(r"https?://[^\s/]*debian\.org/debian(-security)?/?(\s|$)")
ALLOWED = ("main", "contrib", "non-free", "non-free-firmware")


def files(root="/etc/apt"):
    out = [f"{root}/sources.list"] + sorted(glob.glob(f"{root}/sources.list.d/*.list") + glob.glob(f"{root}/sources.list.d/*.sources"))
    return [f for f in out if _readable(f)]


def _readable(p):
    try:
        open(p).close()
        return True
    except OSError:
        return False


def _stanzas(text):
    """deb822: блоковете, разделени с празен ред -> [(начало, край)] в редове."""
    lines, out, start = text.split("\n"), [], None
    for i, l in enumerate(lines + [""]):
        if l.strip() and start is None:
            start = i
        elif not l.strip() and start is not None:
            out.append((start, i))
            start = None
    return lines, out


def _field(lines, a, b, name):
    for i in range(a, b):
        k, _, v = lines[i].partition(":")
        if k.strip().lower() == name.lower() and not lines[i].lstrip().startswith("#"):
            return i, v.strip()
    return None, ""


def components(text, deb822):
    """Компонентите, включени за официалните извори на Debian в един файл."""
    found = set()
    if deb822:
        lines, st = _stanzas(text)
        for a, b in st:
            _, uris = _field(lines, a, b, "URIs")
            _, en = _field(lines, a, b, "Enabled")
            if en.lower() == "no" or not any(DEBIAN_URI.match(u + " ") for u in uris.split()):
                continue
            found |= set(_field(lines, a, b, "Components")[1].split())
    else:
        for l in text.splitlines():
            p = _deb_line(l)
            if p:
                found |= set(p[1])
    return found


def _deb_line(l):
    """„deb [опции] URI suite comp…“ за Debian -> (индекс на първия компонент, компоненти) или None."""
    s = l.strip()
    if not (s.startswith("deb ") or s.startswith("deb-src ")):
        return None
    s = re.sub(r"\[[^\]]*\]", "", s)
    p = s.split()
    if len(p) < 4 or not DEBIAN_URI.match(p[1] + " "):
        return None
    return 3, p[3:]


def add(text, deb822, wanted):
    """Добавя липсващите компоненти към изворите на Debian. Връща (нов текст, променено ли е)."""
    wanted = [c for c in ALLOWED if c in wanted]
    changed = False
    if deb822:
        lines, st = _stanzas(text)
        for a, b in st:
            _, uris = _field(lines, a, b, "URIs")
            _, en = _field(lines, a, b, "Enabled")
            if en.lower() == "no" or not any(DEBIAN_URI.match(u + " ") for u in uris.split()):
                continue
            i, comps = _field(lines, a, b, "Components")
            if i is None:
                continue
            have = comps.split()
            miss = [c for c in wanted if c not in have]
            if miss:
                lines[i] = lines[i].rstrip() + " " + " ".join(miss)
                changed = True
        return "\n".join(lines), changed
    out = []
    for l in text.split("\n"):
        p = _deb_line(l)
        if p:
            miss = [c for c in wanted if c not in p[1]]
            if miss:
                l = l.rstrip() + " " + " ".join(miss)
                changed = True
        out.append(l)
    return "\n".join(out), changed


def enabled(root="/etc/apt"):
    """Всички компоненти, включени за Debian във всички файлове."""
    have = set()
    for f in files(root):
        with open(f, errors="replace") as h:
            have |= components(h.read(), f.endswith(".sources"))
    return have
