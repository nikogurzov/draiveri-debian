"""Поправките: изворите на apt, планът и помощникът (без root и без промени по системата)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import izvori
import jezgro as j
import popravi

LIST = """# deb cdrom:[Debian GNU/Linux 13.0.0]/ trixie main
deb http://deb.debian.org/debian/ trixie main
deb-src http://deb.debian.org/debian/ trixie main
deb http://security.debian.org/debian-security trixie-security main
deb [signed-by=/x.gpg] https://dl.google.com/linux/chrome/deb/ stable main
"""

SOURCES = """Types: deb
URIs: http://deb.debian.org/debian/
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp

Types: deb
URIs: https://dl.google.com/linux/chrome-stable/deb/
Suites: stable
Components: main
"""


class Izvori(unittest.TestCase):
    def test_list_fresh_install(self):
        self.assertEqual(izvori.components(LIST, False), {"main"})
        new, ch = izvori.add(LIST, False, ["non-free-firmware"])
        self.assertTrue(ch)
        self.assertIn("deb http://deb.debian.org/debian/ trixie main non-free-firmware", new)
        self.assertIn("trixie-security main non-free-firmware", new)
        self.assertIn("chrome/deb/ stable main\n", new)            # чуждите извори не се пипат
        self.assertIn("# deb cdrom:[Debian GNU/Linux 13.0.0]/ trixie main\n", new)

    def test_list_twice_no_change(self):
        new, _ = izvori.add(LIST, False, ["non-free-firmware"])
        self.assertEqual(izvori.add(new, False, ["non-free-firmware"]), (new, False))

    def test_options_in_brackets(self):
        t = "deb [arch=amd64] http://ftp.bg.debian.org/debian/ trixie main contrib\n"
        new, ch = izvori.add(t, False, ["non-free", "non-free-firmware", "contrib"])
        self.assertEqual(new, "deb [arch=amd64] http://ftp.bg.debian.org/debian/ trixie main contrib non-free non-free-firmware\n")

    def test_deb822(self):
        self.assertEqual(izvori.components(SOURCES, True), {"main"})
        new, ch = izvori.add(SOURCES, True, ["non-free-firmware"])
        self.assertTrue(ch)
        self.assertIn("Components: main non-free-firmware\nSigned-By", new)
        self.assertTrue(new.rstrip().endswith("Components: main"))  # Chrome остава същият

    def test_files_and_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(d + "/sources.list.d")
            open(d + "/sources.list", "w").write("")
            open(d + "/sources.list.d/debian.sources", "w").write(SOURCES)
            self.assertEqual(izvori.enabled(d), {"main"})


def report(findings, limits=(), kernel="6.12.48+deb13-amd64"):
    r = j.Report(kernel=kernel, findings=list(findings), limits=list(limits))
    return r


class Plan(unittest.TestCase):
    def test_fresh_install(self):
        r = report([j.Finding(j.WARN, "Липсва фърмуер: iwlwifi-ty-a0-gf-a0-89.ucode", "…", "firmware-iwlwifi"),
                    j.Finding(j.WARN, "Липсват поправките за процесора", "…", "amd64-microcode"),
                    j.Finding(j.WARN, "Изворът non-free-firmware не е включен", "…"),
                    j.Finding(j.INFO, "Намерен пакет: tlp", "…", "tlp")],
                   ["Няма lspci, затова …"])
        fixes = j.plan(r)
        self.assertEqual([f.packages for f in fixes], [["firmware-iwlwifi"], ["amd64-microcode"], [], ["tlp"], ["pciutils"]])
        self.assertEqual([f.default for f in fixes], [True, True, True, False, True])
        cmd = j.fix_command([f for f in fixes if f.default], "/x/popravi.py")
        self.assertEqual(cmd, ["pkexec", "/usr/bin/python3", "-I", "/x/popravi.py", "--comp", "non-free-firmware",
                               "--pkg", "firmware-iwlwifi", "--pkg", "amd64-microcode", "--pkg", "pciutils"])
        self.assertEqual(popravi.args(cmd[4:]), (["non-free-firmware"], ["firmware-iwlwifi", "amd64-microcode", "pciutils"], [], set()))

    def test_no_kernel_log_offers_adm(self):
        f, = j.plan(report([], [j.NO_LOG]))
        self.assertTrue(f.adm)
        cmd = j.fix_command([f], "/x/popravi.py")
        self.assertEqual(cmd[-1], "--adm")
        self.assertEqual(popravi.args(cmd[4:])[3], {"--adm"})

    def test_nvidia_on_nouveau_is_optional(self):
        r = report([j.Finding(j.INFO, "Видеокарта NVIDIA", "nouveau")])
        f, = j.plan(r, j.kernel_flavour(r.kernel))
        self.assertFalse(f.default)
        self.assertEqual(f.packages[0], "linux-headers-amd64")
        self.assertEqual(f.components, ["contrib", "non-free", "non-free-firmware"])

    def test_module_fix(self):
        r = report([j.Finding(j.WARN, "Драйвер за X", "…", "", "rtw89_8852ce")])
        f, = j.plan(r)
        self.assertEqual(f.modules, ["rtw89_8852ce"])

    def test_kernel_flavour(self):
        self.assertEqual(j.kernel_flavour("7.1.13+deb13-amd64"), "amd64")
        self.assertEqual(j.kernel_flavour("6.12.48+deb13-rt-amd64"), "rt-amd64")


class Search(unittest.TestCase):
    def test_kernel_findings(self):
        devs = [j.Device("PCI", "Network controller", "Wi-Fi", "", "", j.WARN, "", "pci:v000010ECd0000C852"),
                j.Device("USB", "Камера", "Cam", "", "", j.WARN, "", "usb:v1234p5678"),
                j.Device("PCI", "VGA", "GPU", "amdgpu", "", j.OK, "", "pci:x")]
        res = j.kernel_findings(devs, lambda a: ["rtw89_8852ce"] if a.startswith("pci:v000010EC") else [])
        self.assertEqual([(f.level, f.module) for f in res], [(j.WARN, "rtw89_8852ce"), (j.INFO, "")])

    def test_microcode(self):
        self.assertEqual(j.microcode_findings("vendor_id : AuthenticAMD", set())[0].package, "amd64-microcode")
        self.assertEqual(j.microcode_findings("vendor_id : GenuineIntel", {"intel-microcode"}), [])

    def test_isenkram_skips_installed(self):
        res = j.isenkram_findings(["tlp", "ethtool"], {"ethtool"})
        self.assertEqual([f.package for f in res], ["tlp"])


class History(unittest.TestCase):
    def test_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = d + "/x/istoria.json"
            self.assertEqual(j.history(p), [])
            popravi.save_history([{"packages": ["firmware-iwlwifi"], "backup": "", "adm": ""}], p)
            self.assertEqual(j.history(p)[0]["packages"], ["firmware-iwlwifi"])
            self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o644")

    def test_reset_command(self):
        self.assertEqual(popravi.args(j.reset_command("/x/p.py")[4:])[3], {"--reset"})


class Helper(unittest.TestCase):
    def test_rejects_bad_names(self):
        for bad in (["--pkg", "x; rm -rf /"], ["--comp", "universe"], ["--mod", "a b"], ["--other", "x"]):
            with self.assertRaises(SystemExit):
                popravi.args(bad)



class FixAndReset(unittest.TestCase):
    """Поправи -> върни, с подменени apt/dpkg и временни файлове вместо /etc/apt."""
    def test_roundtrip(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(d + "/apt/sources.list.d")
            open(d + "/apt/sources.list", "w").write(LIST)
            open(d + "/apt/sources.list.d/debian.sources", "w").write(SOURCES)
            state = {"pkgs": {"bash"}}
            calls = []

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[:2] == ["apt-get", "install"]:
                    state["pkgs"] |= set(cmd[3:]) | {"firmware-misc-nonfree"}       # и една зависимост
                if cmd[:2] == ["apt-get", "purge"]:
                    state["pkgs"] -= set(cmd[3:])
                return mock.Mock(returncode=0, stdout="")
            real_files = izvori.files
            with mock.patch.object(popravi, "ISTORIA", d + "/lib/istoria.json"), \
                 mock.patch.object(popravi, "BACKUPS", d + "/backups"), \
                 mock.patch.object(popravi.izvori, "files", lambda: real_files(d + "/apt")), \
                 mock.patch.object(popravi, "installed", lambda: set(state["pkgs"])), \
                 mock.patch.object(popravi.subprocess, "run", fake_run), \
                 mock.patch.object(popravi, "say", lambda s: None):
                popravi.fix(["non-free-firmware"], ["firmware-iwlwifi"], [], False)
                self.assertIn("non-free-firmware", open(d + "/apt/sources.list").read())
                h = popravi.load_history(popravi.ISTORIA)
                self.assertEqual(h[0]["packages"], ["firmware-iwlwifi", "firmware-misc-nonfree"])
                popravi.reset()
            self.assertEqual(open(d + "/apt/sources.list").read(), LIST)
            self.assertEqual(open(d + "/apt/sources.list.d/debian.sources").read(), SOURCES)
            self.assertEqual(state["pkgs"], {"bash"})                    # нищо чуждо не е махнато
            self.assertFalse(os.path.exists(d + "/lib/istoria.json"))
            self.assertIn(["apt-get", "purge", "-y", "firmware-iwlwifi", "firmware-misc-nonfree"], calls)


if __name__ == "__main__":
    unittest.main()
